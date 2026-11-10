from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.models import JobRun, JobStatus, ReportSource
from app.db.repositories import ClanRepository, ReportRepository
from app.db.session import AsyncSessionFactory
from app.integrations.clash.client import (
    ClashApiClient,
    ClashApiError,
    ClashApiForbidden,
    ClashApiRateLimited,
    ClashApiUnavailable,
)
from app.services.clan_sync_service import ClanSyncService
from app.services.notification_service import NotificationService
from app.services.report_builder import ReportBuildError, ReportBuilderService

logger = logging.getLogger(__name__)


def _public_job_error_message(exc: Exception) -> str:
    if isinstance(exc, ClashApiForbidden):
        return "Clash API rejected the request (403). Check the IP allowlist and token."
    if isinstance(exc, ClashApiRateLimited):
        return "Clash API rate limited the request."
    if isinstance(exc, ClashApiUnavailable):
        return "Clash API is temporarily unavailable."
    if isinstance(exc, ClashApiError):
        return "Clash API returned an unexpected error."
    return "Internal error while executing the job."


class AppScheduler:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self.scheduler.add_job(
            self.sync_all_clans_job,
            trigger="interval",
            hours=self.settings.sync_interval_hours,
            id="sync_all_clans",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.auto_reports_job,
            trigger="cron",
            day_of_week="mon",
            hour=self.settings.report_hour,
            minute=self.settings.report_minute,
            id="auto_reports",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("scheduler_started")

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")

    async def sync_all_clans_job(self) -> None:
        async with AsyncSessionFactory() as session:
            run = JobRun(job_name="sync_all_clans", status=JobStatus.RUNNING)
            session.add(run)
            await session.flush()

            try:
                service = ClanSyncService(session=session, clash_client=ClashApiClient())
                snapshots = await service.sync_all_tracking_clans()
                run.status = JobStatus.SUCCESS
                logger.info("sync_all_clans_success", extra={"snapshots": len(snapshots)})
            except Exception as exc:  # noqa: BLE001
                run.status = JobStatus.FAILED
                run.error_message = _public_job_error_message(exc)
                logger.exception("sync_all_clans_failed")
            finally:
                run.finished_at = datetime.now(UTC)
                await session.commit()

    async def auto_reports_job(self) -> None:
        async with AsyncSessionFactory() as session:
            clans = await ClanRepository(session).list_tracking()

        for clan in clans:
            await self.build_report_for_clan_job(clan.tag, source=ReportSource.AUTO, attempt=0)

    async def build_report_for_clan_job(self, clan_tag: str, source: ReportSource, attempt: int) -> None:
        async with AsyncSessionFactory() as session:
            clan = await ClanRepository(session).get_by_tag(clan_tag)
            run = JobRun(
                job_name="build_report",
                clan_id=clan.id if clan else None,
                attempt=attempt,
                status=JobStatus.RUNNING,
            )
            session.add(run)
            await session.flush()

            try:
                builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
                result = await builder.build_report_for_clan(clan_tag, source=source, force_rebuild=False)

                report = await ReportRepository(session).get_by_id(result.report.id)
                if report is None:
                    raise ReportBuildError("Report not found after build")

                await NotificationService(session=session, bot=self.bot).send_report_notifications(report)
                run.status = JobStatus.SUCCESS
                logger.info("build_report_success", extra={"clan_tag": clan_tag, "report_id": report.id})
            except (ClashApiRateLimited, ClashApiUnavailable, ClashApiForbidden, ClashApiError) as exc:
                public_error = _public_job_error_message(exc)
                logger.warning(
                    "build_report_api_error",
                    extra={"clan_tag": clan_tag, "attempt": attempt, "error_type": type(exc).__name__},
                )
                await self._handle_retry_or_fail(session, clan_tag, source, attempt, public_error, run)
            except Exception as exc:  # noqa: BLE001
                run.status = JobStatus.FAILED
                run.error_message = _public_job_error_message(exc)
                logger.exception("build_report_failed", extra={"clan_tag": clan_tag, "attempt": attempt})
            finally:
                run.finished_at = datetime.now(UTC)
                await session.commit()

    async def _handle_retry_or_fail(
        self,
        session,
        clan_tag: str,
        source: ReportSource,
        attempt: int,
        error_message: str,
        run: JobRun,
    ) -> None:
        delays = self.settings.report_retry_delays_minutes
        run.status = JobStatus.FAILED
        run.error_message = error_message

        if attempt < len(delays):
            delay = delays[attempt]
            run_at = datetime.now(UTC) + timedelta(minutes=delay)
            self.scheduler.add_job(
                self.build_report_for_clan_job,
                trigger="date",
                run_date=run_at,
                args=[clan_tag, ReportSource.RETRY, attempt + 1],
                id=f"build_report_retry:{clan_tag}:{attempt + 1}:{int(run_at.timestamp())}",
                replace_existing=False,
            )
            logger.info("build_report_retry_scheduled", extra={"clan_tag": clan_tag, "attempt": attempt + 1, "delay": delay})
            return

        clan = await ClanRepository(session).get_by_tag(clan_tag)
        if clan is not None:
            await NotificationService(session=session, bot=self.bot).send_build_failure_notification(
                clan_tag=clan.tag,
                clan_id=clan.id,
                reason=error_message,
            )
