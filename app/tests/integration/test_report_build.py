from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Clan, Player, PlayerClanState, ReportCategory, ReportSource
from app.db.repositories import ReportRepository, SnapshotRepository
from app.integrations.clash.schemas import ClanMember, RaidMemberStats, RaidSeason
from app.services.report_builder import ReportBuilderService


class FakeClashClient:
    def __init__(self, now: datetime) -> None:
        self.now = now

    async def get_clan_members(self, clan_tag: str) -> list[ClanMember]:
        return [
            ClanMember(tag="#P1", name="P1"),
            ClanMember(tag="#P2", name="P2"),
        ]

    async def get_latest_raid_season(self, clan_tag: str) -> RaidSeason:
        start = self.now - timedelta(days=2)
        end = self.now - timedelta(days=1)
        return RaidSeason(
            start_time=start,
            end_time=end,
            members=[
                RaidMemberStats(tag="#P1", name="P1", attacks=0),
                RaidMemberStats(tag="#P2", name="P2", attacks=3),
                RaidMemberStats(tag="#P3", name="P3", attacks=0),
            ],
            raw={},
        )


@pytest.mark.asyncio
async def test_report_builder_classifies_kick_newbie_and_left_clan() -> None:
    now = datetime.now(UTC)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        p1 = Player(tag="#P1", name="P1", first_seen_at=now - timedelta(days=30), last_seen_at=now)
        p2 = Player(tag="#P2", name="P2", first_seen_at=now - timedelta(days=2), last_seen_at=now)
        p3 = Player(tag="#P3", name="P3", first_seen_at=now - timedelta(days=30), last_seen_at=now)
        session.add_all([p1, p2, p3])
        await session.flush()

        session.add_all(
            [
                PlayerClanState(
                    player_id=p1.id,
                    clan_id=clan.id,
                    first_seen_in_clan_at=now - timedelta(days=30),
                    last_seen_in_clan_at=now,
                    is_current_member=True,
                ),
                PlayerClanState(
                    player_id=p2.id,
                    clan_id=clan.id,
                    first_seen_in_clan_at=now - timedelta(days=1),
                    last_seen_in_clan_at=now,
                    is_current_member=True,
                ),
                PlayerClanState(
                    player_id=p3.id,
                    clan_id=clan.id,
                    first_seen_in_clan_at=now - timedelta(days=30),
                    last_seen_in_clan_at=now,
                    is_current_member=True,
                ),
            ]
        )
        await session.flush()

        await SnapshotRepository(session).create(
            clan_id=clan.id,
            taken_at=now - timedelta(days=1, hours=3),
            member_tags=["#P1", "#P2", "#P3"],
            raw_payload=None,
        )
        await session.commit()

    async with session_factory() as session:
        builder = ReportBuilderService(session=session, clash_client=FakeClashClient(now=now))
        result = await builder.build_report_for_clan("#CLAN", ReportSource.MANUAL, force_rebuild=True)

        report = await ReportRepository(session).get_by_id(result.report.id)
        assert report is not None
        assert report.kick_count == 1
        assert report.newbie_count == 1
        assert report.left_count == 1

        by_tag = {row.player_tag: row for row in report.players}
        assert by_tag["#P1"].category == ReportCategory.KICK
        assert by_tag["#P2"].category == ReportCategory.NEWBIE
        assert by_tag["#P3"].category == ReportCategory.LEFT_CLAN

    await engine.dispose()
