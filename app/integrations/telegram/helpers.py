from dataclasses import dataclass

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Clan, ClanAccess
from app.db.repositories import ClanRepository, UserRepository
from app.services.clan_service import TelegramIdentity


@dataclass(slots=True)
class AccessContext:
    clan: Clan
    access: ClanAccess


async def ensure_user_access(session: AsyncSession, tg_user: TgUser, clan: Clan) -> AccessContext | None:
    users = UserRepository(session)
    clans = ClanRepository(session)
    user = await users.get_by_telegram_id(tg_user.id)
    if user is None:
        return None
    access = await clans.get_access(clan.id, user.id)
    if access is None:
        return None
    return AccessContext(clan=clan, access=access)


def telegram_identity(user: TgUser) -> TelegramIdentity:
    return TelegramIdentity(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
