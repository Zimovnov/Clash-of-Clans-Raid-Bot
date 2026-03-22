from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import RaidReport, RaidReportPlayer, ReportSource, ReportStatus


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_for_clan(self, clan_id: int) -> RaidReport | None:
        stmt = (
            select(RaidReport)
            .where(RaidReport.clan_id == clan_id, RaidReport.status == ReportStatus.SUCCESS)
            .order_by(RaidReport.generated_at.desc())
            .limit(1)
            .options(selectinload(RaidReport.players), selectinload(RaidReport.clan))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_for_clan_and_period(self, clan_id: int, period_end_at: datetime | None) -> RaidReport | None:
        stmt = (
            select(RaidReport)
            .where(
                RaidReport.clan_id == clan_id,
                RaidReport.raid_weekend_end_at == period_end_at,
                RaidReport.status == ReportStatus.SUCCESS,
            )
            .order_by(RaidReport.generated_at.desc())
            .limit(1)
            .options(selectinload(RaidReport.players), selectinload(RaidReport.clan))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_report(
        self,
        clan_id: int,
        source: ReportSource,
        raid_weekend_start_at: datetime | None,
        raid_weekend_end_at: datetime | None,
    ) -> RaidReport:
        report = RaidReport(
            clan_id=clan_id,
            source=source,
            status=ReportStatus.SUCCESS,
            raid_weekend_start_at=raid_weekend_start_at,
            raid_weekend_end_at=raid_weekend_end_at,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def create_failed_report(
        self,
        clan_id: int,
        source: ReportSource,
        error_message: str,
    ) -> RaidReport:
        report = RaidReport(
            clan_id=clan_id,
            source=source,
            status=ReportStatus.FAILED,
            error_message=error_message,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def add_player_rows(self, report_id: int, rows: list[RaidReportPlayer]) -> None:
        for row in rows:
            row.report_id = report_id
            self.session.add(row)
        await self.session.flush()

    async def get_by_id(self, report_id: int) -> RaidReport | None:
        stmt = (
            select(RaidReport)
            .where(RaidReport.id == report_id)
            .options(selectinload(RaidReport.players), selectinload(RaidReport.clan))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
