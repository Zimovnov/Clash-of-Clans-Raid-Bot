from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.integrations.telegram.command_menu import resolve_command_permissions, sync_user_command_menu

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot) -> None:
    if message.from_user is not None:
        await sync_user_command_menu(bot, message.from_user.id)

    await message.answer(
        "Сервис предназначен для контроля рейд-выходных Clan Capital.\n"
        "Для подключения клана используйте /addclan <TAG>.\n"
        "Команды доступны в меню Telegram и по /help."
    )


def build_help_text(*, has_clan_access: bool, can_manage_access: bool, is_superadmin: bool) -> str:
    lines = [
        "Основные команды:",
        "/addclan <TAG> - подключить клан",
        "/myclans - список доступных кланов",
        "/clan <TAG> - карточка клана",
        "/report [TAG] - открыть отчёт",
    ]

    if has_clan_access:
        lines.extend(
            [
                "",
                "Работа с кланом:",
                "/roles <TAG> - права доступа",
                "/note <CLAN_TAG> <PLAYER_TAG> <ТЕКСТ> - примечание по игроку",
            ]
        )

    if can_manage_access:
        lines.extend(
            [
                "",
                "Управление доступом:",
                "/requests <TAG> - заявки на доступ",
                "/grant_manager <CLAN_TAG> <TELEGRAM_ID> - выдать manager",
                "/revoke_access <CLAN_TAG> <TELEGRAM_ID> - отозвать доступ",
            ]
        )

    if is_superadmin:
        lines.extend(
            [
                "",
                "Команда superadmin:",
                "/transfer_owner <CLAN_TAG> <TELEGRAM_ID> - сменить владельца",
            ]
        )

    return "\n".join(lines)


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return

    await sync_user_command_menu(bot, message.from_user.id)
    has_clan_access, can_manage_access, is_superadmin = await resolve_command_permissions(message.from_user.id)
    await message.answer(
        build_help_text(
            has_clan_access=has_clan_access,
            can_manage_access=can_manage_access,
            is_superadmin=is_superadmin,
        )
    )
