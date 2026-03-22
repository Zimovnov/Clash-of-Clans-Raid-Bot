from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tags import normalize_tag
from app.db.models import RaidReport, RaidReportPlayer, ReportCategory, ReportSource
from app.db.repositories import ClanRepository, PlayerRepository, ReportRepository, SnapshotRepository
from app.integrations.clash.client import ClashApiClient
from app.integrations.clash.schemas import RaidMemberStats, RaidSeason
from app.services.classifier import ClassificationContext, PlayerClassificationInput, classify_player
from app.services.clan_sync_service import ClanSyncService


class ReportBuildError(Exception):
    pass


@dataclass(slots=True)
class ReportBuildResult:
    report: RaidReport
    is_cached: bool


class ReportBuilderService:
    def __init__(self, session: AsyncSession, clash_client: ClashApiClient) -> None:
        self.session = session
        self.clash_client = clash_client
        self.clans = ClanRepository(session)
        self.players = PlayerRepository(session)
        self.reports = ReportRepository(session)
        self.snapshots = SnapshotRepository(session)
        self.sync_service = ClanSyncService(session, clash_client)

    async def build_report_for_clan(
        self,
        raw_clan_tag: str,
        source: ReportSource,
        force_rebuild: bool = False,
    ) -> ReportBuildResult:
        clan_tag = normalize_tag(raw_clan_tag)
        clan = await self.clans.get_by_tag(clan_tag)
        if clan is None:
            raise ReportBuildError(f"Clan not found: {clan_tag}")

        await self.sync_service.sync_clan(clan.tag)
        raid = await self.clash_client.get_latest_raid_season(clan.tag)
        if raid is None:
            raise ReportBuildError("No raid season data available")

        if not force_rebuild:
            existing = await self.reports.latest_for_clan_and_period(clan.id, raid.end_time)
            if existing:
                return ReportBuildResult(report=existing, is_cached=True)

        now = datetime.now(UTC)
        raid_start_at, raid_end_at = self._resolve_raid_window(raid=raid, now=now)
        snapshots = await self.snapshots.list_between(clan.id, raid_start_at, now)
        latest_snapshot = await self.snapshots.latest(clan.id)

        snapshot_tags: set[str] = set()
        for snapshot in snapshots:
            snapshot_tags.update(snapshot.member_tags)

        current_tags = set(latest_snapshot.member_tags if latest_snapshot else [])
        raid_members_by_tag = self._normalize_raid_members(raid.members)

        observed_tags = snapshot_tags | current_tags | set(raid_members_by_tag.keys())
        states = await self.players.list_states_for_clan(clan.id)
        states_by_tag = {state.player.tag: state for state in states if state.player is not None}

        existing_players = await self.players.list_by_tags(sorted(observed_tags))
        players_by_tag = {player.tag: player for player in existing_players}

        report = await self.reports.create_report(
            clan_id=clan.id,
            source=source,
            raid_weekend_start_at=raid_start_at,
            raid_weekend_end_at=raid_end_at,
        )

        ctx = ClassificationContext(
            now=now,
            raid_start_at=raid_start_at,
            newbie_window_days=7,
            newbie_baseline_at=clan.newbie_baseline_at,
        )
        rows: list[RaidReportPlayer] = []
        counters = {
            ReportCategory.KICK: 0,
            ReportCategory.QUESTIONABLE: 0,
            ReportCategory.NEWBIE: 0,
            ReportCategory.LEFT_CLAN: 0,
            ReportCategory.OK: 0,
        }

        for tag in sorted(observed_tags):
            raid_member = raid_members_by_tag.get(tag)
            state = states_by_tag.get(tag)
            player = players_by_tag.get(tag) or (state.player if state else None)

            attacks_used = raid_member.attacks if raid_member else 0
            player_name = (
                raid_member.name
                if raid_member
                else (player.name if player is not None else tag)
            )
            first_seen_in_clan_at = state.first_seen_in_clan_at if state else None
            is_current_member = tag in current_tags if current_tags else bool(state and state.is_current_member)
            was_seen_during_raid = tag in snapshot_tags or tag in raid_members_by_tag

            classification_input = PlayerClassificationInput(
                tag=tag,
                name=player_name,
                attacks_used=attacks_used,
                is_current_member=is_current_member,
                was_seen_during_raid=was_seen_during_raid,
                first_seen_in_clan_at=first_seen_in_clan_at,
            )
            classification = classify_player(classification_input, ctx)
            counters[classification.category] += 1

            rows.append(
                RaidReportPlayer(
                    report_id=report.id,
                    player_id=player.id if player else None,
                    player_tag=tag,
                    player_name=player_name,
                    attacks_used=attacks_used,
                    category=classification.category,
                    is_current_member=is_current_member,
                    first_seen_in_clan_at=first_seen_in_clan_at,
                    left_clan_note=(
                        "Player was seen during raid window but is no longer in clan"
                        if classification.category == ReportCategory.LEFT_CLAN
                        else None
                    ),
                )
            )

        report.kick_count = counters[ReportCategory.KICK]
        report.question_count = counters[ReportCategory.QUESTIONABLE]
        report.newbie_count = counters[ReportCategory.NEWBIE]
        report.left_count = counters[ReportCategory.LEFT_CLAN]
        report.ok_count = counters[ReportCategory.OK]

        await self.reports.add_player_rows(report.id, rows)
        await self.session.commit()
        await self.session.refresh(report)

        return ReportBuildResult(report=report, is_cached=False)

    @staticmethod
    def _resolve_raid_window(raid: RaidSeason, now: datetime) -> tuple[datetime, datetime | None]:
        if raid.start_time and raid.end_time:
            return raid.start_time, raid.end_time
        if raid.end_time and not raid.start_time:
            return raid.end_time - timedelta(days=3), raid.end_time
        return now - timedelta(days=7), raid.end_time

    @staticmethod
    def _normalize_raid_members(members: list[RaidMemberStats]) -> dict[str, RaidMemberStats]:
        normalized: dict[str, RaidMemberStats] = {}
        for member in members:
            tag = normalize_tag(member.tag)
            normalized[tag] = member
        return normalized
