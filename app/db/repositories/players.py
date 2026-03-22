from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Player, PlayerClanState


class PlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tag(self, tag: str) -> Player | None:
        stmt = select(Player).where(Player.tag == tag)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(self, tag: str, name: str, now: datetime) -> Player:
        player = await self.get_by_tag(tag)
        if player:
            player.name = name
            player.last_seen_at = now
            await self.session.flush()
            return player

        player = Player(tag=tag, name=name, first_seen_at=now, last_seen_at=now)
        self.session.add(player)
        await self.session.flush()
        return player

    async def get_state(self, clan_id: int, player_id: int) -> PlayerClanState | None:
        stmt = select(PlayerClanState).where(
            PlayerClanState.clan_id == clan_id,
            PlayerClanState.player_id == player_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_state_by_player_tag(self, clan_id: int, player_tag: str) -> PlayerClanState | None:
        stmt = (
            select(PlayerClanState)
            .join(Player, Player.id == PlayerClanState.player_id)
            .where(PlayerClanState.clan_id == clan_id, Player.tag == player_tag)
            .options(selectinload(PlayerClanState.player))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_state(self, clan_id: int, player_id: int, now: datetime, is_current_member: bool) -> PlayerClanState:
        state = await self.get_state(clan_id=clan_id, player_id=player_id)
        if state:
            state.last_seen_in_clan_at = now
            state.is_current_member = is_current_member
            await self.session.flush()
            return state

        state = PlayerClanState(
            clan_id=clan_id,
            player_id=player_id,
            first_seen_in_clan_at=now,
            last_seen_in_clan_at=now,
            is_current_member=is_current_member,
        )
        self.session.add(state)
        await self.session.flush()
        return state

    async def list_states_for_clan(self, clan_id: int) -> list[PlayerClanState]:
        stmt = (
            select(PlayerClanState)
            .where(PlayerClanState.clan_id == clan_id)
            .options(selectinload(PlayerClanState.player))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tags(self, tags: list[str]) -> list[Player]:
        if not tags:
            return []
        stmt = select(Player).where(Player.tag.in_(tags))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_manager_note(self, clan_id: int, player_tag: str, note: str | None) -> PlayerClanState | None:
        state = await self.get_state_by_player_tag(clan_id=clan_id, player_tag=player_tag)
        if state is None:
            return None
        state.manager_note = note
        await self.session.flush()
        return state
