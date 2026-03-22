from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerProfile


class PlayerProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_player_id(self, player_id: int) -> PlayerProfile | None:
        stmt = select(PlayerProfile).where(PlayerProfile.player_id == player_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        player_id: int,
        exp_level: int | None,
        town_hall_level: int | None,
        builder_hall_level: int | None,
        league_name: str | None,
        clan_role: str | None,
        refreshed_at: datetime,
        raw_payload: dict | None,
    ) -> PlayerProfile:
        profile = await self.get_by_player_id(player_id)
        if profile is None:
            profile = PlayerProfile(
                player_id=player_id,
                exp_level=exp_level,
                town_hall_level=town_hall_level,
                builder_hall_level=builder_hall_level,
                league_name=league_name,
                clan_role=clan_role,
                refreshed_at=refreshed_at,
                raw_payload=raw_payload,
            )
            self.session.add(profile)
            await self.session.flush()
            return profile

        profile.exp_level = exp_level
        profile.town_hall_level = town_hall_level
        profile.builder_hall_level = builder_hall_level
        profile.league_name = league_name
        profile.clan_role = clan_role
        profile.refreshed_at = refreshed_at
        profile.raw_payload = raw_payload
        await self.session.flush()
        return profile
