from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Player, PlayerProfile
from app.db.repositories import PlayerProfileRepository
from app.integrations.clash.client import ClashApiClient


PROFILE_TTL_HOURS = 24


@dataclass(slots=True)
class PlayerProfileResult:
    profile: PlayerProfile | None
    refreshed: bool


class PlayerProfileService:
    def __init__(self, session: AsyncSession, clash_client: ClashApiClient) -> None:
        self.session = session
        self.clash_client = clash_client
        self.profiles = PlayerProfileRepository(session)

    async def get_for_player(
        self,
        player: Player,
        *,
        refresh_if_missing: bool,
        force_refresh: bool = False,
    ) -> PlayerProfileResult:
        profile = await self.profiles.get_by_player_id(player.id)

        if force_refresh or (profile is None and refresh_if_missing):
            profile = await self.refresh_player(player)
            return PlayerProfileResult(profile=profile, refreshed=True)

        return PlayerProfileResult(profile=profile, refreshed=False)

    async def refresh_player(self, player: Player) -> PlayerProfile:
        payload = await self.clash_client.get_player_profile(player.tag)
        profile = await self.profiles.upsert(
            player_id=player.id,
            exp_level=payload.exp_level,
            town_hall_level=payload.town_hall_level,
            builder_hall_level=payload.builder_hall_level,
            league_name=payload.league_name,
            clan_role=payload.clan_role,
            refreshed_at=datetime.now(UTC),
            raw_payload=payload.raw,
        )
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    @staticmethod
    def is_stale(profile: PlayerProfile | None) -> bool:
        if profile is None:
            return True

        refreshed_at = profile.refreshed_at
        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=UTC)
        return refreshed_at < datetime.now(UTC) - timedelta(hours=PROFILE_TTL_HOURS)
