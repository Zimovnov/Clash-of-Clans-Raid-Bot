from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClanMembershipSnapshot


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, clan_id: int, taken_at: datetime, member_tags: list[str], raw_payload: dict | None) -> ClanMembershipSnapshot:
        snapshot = ClanMembershipSnapshot(
            clan_id=clan_id,
            taken_at=taken_at,
            member_count=len(member_tags),
            member_tags=member_tags,
            raw_payload=raw_payload,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def list_between(self, clan_id: int, start_at: datetime, end_at: datetime) -> list[ClanMembershipSnapshot]:
        stmt = (
            select(ClanMembershipSnapshot)
            .where(
                ClanMembershipSnapshot.clan_id == clan_id,
                ClanMembershipSnapshot.taken_at >= start_at,
                ClanMembershipSnapshot.taken_at <= end_at,
            )
            .order_by(ClanMembershipSnapshot.taken_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest(self, clan_id: int) -> ClanMembershipSnapshot | None:
        stmt = (
            select(ClanMembershipSnapshot)
            .where(ClanMembershipSnapshot.clan_id == clan_id)
            .order_by(ClanMembershipSnapshot.taken_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
