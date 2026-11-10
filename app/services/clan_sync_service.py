from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tags import normalize_tag
from app.db.models import ClanMembershipSnapshot
from app.db.repositories import ClanRepository, PlayerRepository, SnapshotRepository
from app.integrations.clash.client import ClashApiClient


class ClanSyncError(Exception):
    pass


class ClanSyncService:
    def __init__(self, session: AsyncSession, clash_client: ClashApiClient) -> None:
        self.session = session
        self.clash_client = clash_client
        self.clans = ClanRepository(session)
        self.players = PlayerRepository(session)
        self.snapshots = SnapshotRepository(session)

    async def sync_clan(self, raw_clan_tag: str) -> ClanMembershipSnapshot:
        clan_tag = normalize_tag(raw_clan_tag)
        clan = await self.clans.get_by_tag(clan_tag)
        if clan is None:
            raise ClanSyncError(f"Clan not found: {clan_tag}")

        now = datetime.now(UTC)
        members = await self.clash_client.get_clan_members(clan_tag)
        seen_tags: set[str] = set()

        for member in members:
            tag = normalize_tag(member.tag)
            seen_tags.add(tag)
            player = await self.players.get_or_create(tag=tag, name=member.name, now=now)
            await self.players.upsert_state(clan_id=clan.id, player_id=player.id, now=now, is_current_member=True)

        states = await self.players.list_states_for_clan(clan.id)
        for state in states:
            if state.player.tag not in seen_tags and state.is_current_member:
                state.is_current_member = False

        snapshot = await self.snapshots.create(
            clan_id=clan.id,
            taken_at=now,
            member_tags=sorted(seen_tags),
            raw_payload={"members": [asdict(m) for m in members]},
        )
        await self.session.commit()
        return snapshot

    async def sync_all_tracking_clans(self) -> list[ClanMembershipSnapshot]:
        result: list[ClanMembershipSnapshot] = []
        tracking = await self.clans.list_tracking()
        for clan in tracking:
            result.append(await self.sync_clan(clan.tag))
        return result
