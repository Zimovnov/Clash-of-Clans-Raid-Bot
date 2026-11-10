from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.core.config import get_settings
from app.core.i18n import DEFAULT_LANGUAGE, normalize_language, t
from app.db.models import ClanRole
from app.db.repositories import ClanRepository, UserRepository
from app.db.session import AsyncSessionFactory


def build_command_menu(
    *,
    lang: str,
    has_clan_access: bool,
    can_review_requests: bool,
    can_manage_access: bool,
    is_superadmin: bool,
) -> list[BotCommand]:
    commands = [
        BotCommand(command="start", description=t(lang, "command_desc.start")),
        BotCommand(command="help", description=t(lang, "command_desc.help")),
        BotCommand(command="english", description=t(lang, "command_desc.english")),
        BotCommand(command="russian", description=t(lang, "command_desc.russian")),
        BotCommand(command="addclan", description=t(lang, "command_desc.addclan")),
        BotCommand(command="myclans", description=t(lang, "command_desc.myclans")),
        BotCommand(command="report", description=t(lang, "command_desc.report")),
    ]

    if has_clan_access:
        commands.extend(
            [
                BotCommand(command="roles", description=t(lang, "command_desc.roles")),
                BotCommand(command="note", description=t(lang, "command_desc.note")),
                BotCommand(command="leave_access", description=t(lang, "command_desc.leave_access")),
            ]
        )

    if can_review_requests:
        commands.append(BotCommand(command="requests", description=t(lang, "command_desc.requests")))

    if can_manage_access:
        commands.extend(
            [
                BotCommand(command="grant_manager", description=t(lang, "command_desc.grant_manager")),
                BotCommand(command="revoke_access", description=t(lang, "command_desc.revoke_access")),
            ]
        )

    if is_superadmin:
        commands.append(BotCommand(command="transfer_owner", description=t(lang, "command_desc.transfer_owner")))

    return commands


async def resolve_command_permissions(telegram_id: int) -> tuple[bool, bool, bool, bool, str]:
    settings = get_settings()
    is_superadmin = telegram_id in settings.superadmin_telegram_ids

    async with AsyncSessionFactory() as session:
        users = UserRepository(session)
        user = await users.get_by_telegram_id(telegram_id)
        lang = normalize_language(user.language if user is not None else DEFAULT_LANGUAGE).value
        if is_superadmin:
            return True, True, True, True, lang
        if user is None:
            return False, False, False, False, lang
        clans = ClanRepository(session)
        has_clan_access = await clans.has_any_access_for_user(user.id)
        can_review_requests = await clans.has_role_for_user(user.id, ClanRole.OWNER) or await clans.has_ownerless_manager_access_for_user(user.id)
        can_manage_access = await clans.has_role_for_user(user.id, ClanRole.OWNER)
        return has_clan_access, can_review_requests, can_manage_access, False, lang


async def sync_user_command_menu(bot: Bot, telegram_id: int) -> None:
    has_clan_access, can_review_requests, can_manage_access, is_superadmin, lang = await resolve_command_permissions(telegram_id)
    commands = build_command_menu(
        lang=lang,
        has_clan_access=has_clan_access,
        can_review_requests=can_review_requests,
        can_manage_access=can_manage_access,
        is_superadmin=is_superadmin,
    )
    await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=telegram_id))


async def setup_command_menus(bot: Bot) -> None:
    default_commands = build_command_menu(
        lang=DEFAULT_LANGUAGE.value,
        has_clan_access=False,
        can_review_requests=False,
        can_manage_access=False,
        is_superadmin=False,
    )
    await bot.set_my_commands(default_commands, scope=BotCommandScopeAllPrivateChats())

    async with AsyncSessionFactory() as session:
        telegram_ids = await UserRepository(session).list_telegram_ids()

    for telegram_id in telegram_ids:
        await sync_user_command_menu(bot, telegram_id)
