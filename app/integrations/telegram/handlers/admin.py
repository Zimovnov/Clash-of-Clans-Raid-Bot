from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.integrations.clash.client import ClashApiClient
from app.integrations.telegram.command_menu import sync_user_command_menu
from app.services.clan_service import ClanService, ClanServiceError

router = Router(name="admin")


@router.message(Command("transfer_owner"))
async def cmd_transfer_owner(message: Message, command: CommandObject, bot: Bot) -> None:
    if message.from_user is None:
        return

    settings = get_settings()
    if message.from_user.id not in settings.superadmin_telegram_ids:
        await message.answer("Команда доступна только superadmin.")
        return

    if not command.args:
        await message.answer("Использование: /transfer_owner <CLAN_TAG> <TELEGRAM_ID>")
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.answer("Использование: /transfer_owner <CLAN_TAG> <TELEGRAM_ID>")
        return

    clan_tag, telegram_id_raw = parts
    try:
        telegram_id = int(telegram_id_raw)
    except ValueError:
        await message.answer("TELEGRAM_ID должен быть числом.")
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            clan = await service.transfer_owner(clan_tag, telegram_id)
        except ClanServiceError as exc:
            await message.answer(f"Ошибка: {exc}")
            return

    await sync_user_command_menu(bot, telegram_id)
    await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(f"Владелец клана {clan.name} ({clan.tag}) изменён. Новый владелец: {telegram_id}.")
