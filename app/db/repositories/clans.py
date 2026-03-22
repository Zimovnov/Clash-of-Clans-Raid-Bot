from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Clan, ClanAccess, ClanRole


class ClanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tag(self, tag: str) -> Clan | None:
        stmt = select(Clan).where(Clan.tag == tag)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tag: str, name: str) -> Clan:
        clan = Clan(tag=tag, name=name, is_tracking=True)
        self.session.add(clan)
        await self.session.flush()
        return clan

    async def list_for_user(self, user_id: int) -> list[Clan]:
        stmt = (
            select(Clan)
            .join(ClanAccess, ClanAccess.clan_id == Clan.id)
            .where(ClanAccess.user_id == user_id)
            .order_by(Clan.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tracking(self) -> list[Clan]:
        stmt = select(Clan).where(Clan.is_tracking.is_(True)).order_by(Clan.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def grant_role(self, clan_id: int, user_id: int, role: ClanRole) -> ClanAccess:
        stmt = select(ClanAccess).where(ClanAccess.clan_id == clan_id, ClanAccess.user_id == user_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.role = role
            await self.session.flush()
            return existing

        access = ClanAccess(clan_id=clan_id, user_id=user_id, role=role)
        self.session.add(access)
        await self.session.flush()
        return access

    async def get_access(self, clan_id: int, user_id: int) -> ClanAccess | None:
        stmt = select(ClanAccess).where(ClanAccess.clan_id == clan_id, ClanAccess.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def has_role_for_user(self, user_id: int, role: ClanRole) -> bool:
        stmt = select(ClanAccess.id).where(ClanAccess.user_id == user_id, ClanAccess.role == role).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_any_access_for_user(self, user_id: int) -> bool:
        stmt = select(ClanAccess.id).where(ClanAccess.user_id == user_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_accesses(self, clan_id: int) -> list[ClanAccess]:
        stmt = (
            select(ClanAccess)
            .where(ClanAccess.clan_id == clan_id)
            .options(selectinload(ClanAccess.user))
            .order_by(ClanAccess.role.asc(), ClanAccess.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_accesses_by_role(self, clan_id: int, role: ClanRole) -> list[ClanAccess]:
        stmt = (
            select(ClanAccess)
            .where(ClanAccess.clan_id == clan_id, ClanAccess.role == role)
            .options(selectinload(ClanAccess.user))
            .order_by(ClanAccess.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def revoke_access(self, clan_id: int, user_id: int) -> None:
        await self.session.execute(delete(ClanAccess).where(ClanAccess.clan_id == clan_id, ClanAccess.user_id == user_id))
        await self.session.flush()

    async def transfer_owner(self, clan_id: int, new_owner_user_id: int) -> None:
        await self.session.execute(
            delete(ClanAccess).where(ClanAccess.clan_id == clan_id, ClanAccess.role == ClanRole.OWNER)
        )
        self.session.add(ClanAccess(clan_id=clan_id, user_id=new_owner_user_id, role=ClanRole.OWNER))
        await self.session.flush()
