from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import format_datetime_human
from app.db.models import OutboxMessage, OutboxStatus, RaidReport
from app.db.repositories import ClanRepository

logger = logging.getLogger(__name__)


def _public_delivery_error_message() -> str:
    return "Telegram delivery failed."


class NotificationService:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self.session = session
        self.bot = bot
        self.clans = ClanRepository(session)

    async def send_report_notifications(self, report: RaidReport) -> None:
        accesses = await self.clans.list_accesses(report.clan_id)
        text = self._build_report_text(report)

        for access in accesses:
            dedupe_key = f"report:{report.id}:user:{access.user_id}"
            if await self._is_already_sent(dedupe_key):
                continue

            outbox = OutboxMessage(
                clan_id=report.clan_id,
                user_id=access.user_id,
                report_id=report.id,
                message_type="raid_report",
                dedupe_key=dedupe_key,
                status=OutboxStatus.PENDING,
                payload={"text": text},
            )
            self.session.add(outbox)
            await self.session.flush()

            try:
                message = await self.bot.send_message(chat_id=access.user.telegram_id, text=text)
                outbox.status = OutboxStatus.SENT
                outbox.telegram_message_id = message.message_id
                outbox.sent_at = datetime.now(UTC)
                logger.info("report_notification_sent", extra={"report_id": report.id, "user_id": access.user_id})
            except Exception:  # noqa: BLE001
                outbox.status = OutboxStatus.FAILED
                outbox.error_message = _public_delivery_error_message()
                logger.exception("report_notification_failed", extra={"report_id": report.id, "user_id": access.user_id})

        await self.session.commit()

    async def send_build_failure_notification(self, clan_tag: str, clan_id: int, reason: str) -> None:
        accesses = await self.clans.list_accesses(clan_id)
        text = f"Автоматический отчёт для {clan_tag} не сформирован. Причина: {reason}"

        for access in accesses:
            dedupe_key = f"report_failure:{clan_tag}:user:{access.user_id}:{datetime.now(UTC).date()}"
            if await self._is_message_exists(dedupe_key):
                continue
            outbox = OutboxMessage(
                clan_id=clan_id,
                user_id=access.user_id,
                report_id=None,
                message_type="report_failure",
                dedupe_key=dedupe_key,
                status=OutboxStatus.PENDING,
                payload={"text": text},
            )
            self.session.add(outbox)
            await self.session.flush()

            try:
                message = await self.bot.send_message(chat_id=access.user.telegram_id, text=text)
                outbox.status = OutboxStatus.SENT
                outbox.telegram_message_id = message.message_id
                outbox.sent_at = datetime.now(UTC)
            except Exception:  # noqa: BLE001
                outbox.status = OutboxStatus.FAILED
                outbox.error_message = _public_delivery_error_message()
                logger.exception("report_failure_notification_failed", extra={"clan_id": clan_id, "user_id": access.user_id})

        await self.session.commit()

    async def _is_already_sent(self, dedupe_key: str) -> bool:
        stmt = select(OutboxMessage.id).where(
            OutboxMessage.dedupe_key == dedupe_key,
            OutboxMessage.status == OutboxStatus.SENT,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def _is_message_exists(self, dedupe_key: str) -> bool:
        stmt = select(OutboxMessage.id).where(OutboxMessage.dedupe_key == dedupe_key)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    def _build_report_text(self, report: RaidReport) -> str:
        raid_period = "не указан"
        if report.raid_weekend_start_at and report.raid_weekend_end_at:
            raid_period = f"{format_datetime_human(report.raid_weekend_start_at)} - {format_datetime_human(report.raid_weekend_end_at)}"

        return (
            f"Отчёт по клану {report.clan.tag} ({report.clan.name})\n"
            f"Период рейда: {raid_period}\n"
            f"Сгенерирован: {format_datetime_human(report.generated_at)}\n\n"
            f"На кик: {report.kick_count}\n"
            f"Под вопросом: {report.question_count}\n"
            f"Новички: {report.newbie_count}\n"
            f"Покинули клан: {report.left_count}"
        )
