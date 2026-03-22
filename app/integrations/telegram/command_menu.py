from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.core.config import get_settings
from app.db.models import ClanRole
from app.db.repositories import ClanRepository, UserRepository
from app.db.session import AsyncSessionFactory


def build_command_menu(*, has_clan_access: bool, can_manage_access: bool, is_superadmin: bool) -> list[BotCommand]:
    commands = [
        BotCommand(command="start", description="Главная информация"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="addclan", description="Подключить клан"),
        BotCommand(command="myclans", description="Список кланов"),
        BotCommand(command="clan", description="Карточка клана"),
        BotCommand(command="report", description="Открыть отчёт"),
    ]

    if has_clan_access:
        commands.extend(
            [
                BotCommand(command="roles", description="Права доступа"),
                BotCommand(command="note", description="Примечание по игроку"),
            ]
        )

    if can_manage_access:
        commands.extend(
            [
                BotCommand(command="requests", description="Доступ к боту"),
                BotCommand(command="grant_manager", description="Выдать manager"),
                BotCommand(command="revoke_access", description="Отозвать доступ"),
            ]
        )

    if is_superadmin:
        commands.append(BotCommand(command="transfer_owner", description="Сменить владельца"))

    return commands


async def resolve_command_permissions(telegram_id: int) -> tuple[bool, bool, bool]:
    settings = get_settings()
    is_superadmin = telegram_id in settings.superadmin_telegram_ids
    if is_superadmin:
        return True, True, True

    async with AsyncSessionFactory() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None:
            return False, False, False
        clans = ClanRepository(session)
        has_clan_access = await clans.has_any_access_for_user(user.id)
        can_manage_access = await clans.has_role_for_user(user.id, ClanRole.OWNER)
        return has_clan_access, can_manage_access, False


async def sync_user_command_menu(bot: Bot, telegram_id: int) -> None:
    has_clan_access, can_manage_access, is_superadmin = await resolve_command_permissions(telegram_id)
    commands = build_command_menu(
        has_clan_access=has_clan_access,
        can_manage_access=can_manage_access,
        is_superadmin=is_superadmin,
    )
    await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=telegram_id))


async def setup_command_menus(bot: Bot) -> None:
    default_commands = build_command_menu(has_clan_access=False, can_manage_access=False, is_superadmin=False)
    await bot.set_my_commands(default_commands, scope=BotCommandScopeAllPrivateChats())

    async with AsyncSessionFactory() as session:
        telegram_ids = await UserRepository(session).list_telegram_ids()

    for telegram_id in telegram_ids:
        await sync_user_command_menu(bot, telegram_id)
