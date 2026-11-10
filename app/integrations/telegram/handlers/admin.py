from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.config import get_settings
from app.core.i18n import t, translate_service_error
from app.db.session import AsyncSessionFactory
from app.integrations.clash.client import ClashApiClient
from app.integrations.telegram.command_menu import sync_user_command_menu
from app.services.clan_service import ClanService, ClanServiceError

router = Router(name="admin")


@router.message(Command("transfer_owner"))
async def cmd_transfer_owner(message: Message, command: CommandObject, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return

    settings = get_settings()
    if message.from_user.id not in settings.superadmin_telegram_ids:
        await message.answer(t(lang, "admin.superadmin_only"))
        return

    if not command.args:
        await message.answer(t(lang, "admin.transfer_usage"))
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.answer(t(lang, "admin.transfer_usage"))
        return

    clan_tag, telegram_id_raw = parts
    try:
        telegram_id = int(telegram_id_raw)
    except ValueError:
        await message.answer(t(lang, "general.invalid_telegram_id"))
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            clan = await service.transfer_owner(clan_tag, telegram_id)
        except ClanServiceError as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return

    await sync_user_command_menu(bot, telegram_id)
    await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(t(lang, "admin.transfer_confirm", clan_name=clan.name, clan_tag=clan.tag, telegram_id=telegram_id))
