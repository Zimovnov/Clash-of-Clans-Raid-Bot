from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.i18n import UserLanguage, t
from app.db.repositories import UserRepository
from app.db.session import AsyncSessionFactory
from app.integrations.telegram.command_menu import resolve_command_permissions, sync_user_command_menu

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot, lang: str) -> None:
    if message.from_user is not None:
        await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(t(lang, "common.start"))


async def _set_language_and_confirm(message: Message, bot: Bot, language: UserLanguage, confirmation_key: str) -> None:
    if message.from_user is None:
        return

    async with AsyncSessionFactory() as session:
        await UserRepository(session).set_language(message.from_user.id, language)
        await session.commit()

    await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(t(language.value, confirmation_key))


@router.message(Command("english"))
async def cmd_english(message: Message, bot: Bot) -> None:
    await _set_language_and_confirm(message, bot, UserLanguage.EN, "common.language_changed_en")


@router.message(Command("russian"))
async def cmd_russian(message: Message, bot: Bot) -> None:
    await _set_language_and_confirm(message, bot, UserLanguage.RU, "common.language_changed_ru")


def build_help_text(
    *,
    lang: str,
    has_clan_access: bool,
    can_review_requests: bool,
    can_manage_access: bool,
    is_superadmin: bool,
) -> str:
    lines = [
        t(lang, "help.main"),
        t(lang, "help.addclan"),
        t(lang, "help.myclans"),
        t(lang, "help.report"),
        "",
        t(lang, "help.languages"),
        t(lang, "help.english"),
        t(lang, "help.russian"),
    ]

    if has_clan_access:
        lines.extend(
            [
                "",
                t(lang, "help.clan"),
                t(lang, "help.roles"),
                t(lang, "help.note"),
                t(lang, "help.leave_access"),
            ]
        )

    if can_review_requests or can_manage_access:
        lines.extend(
            [
                "",
                t(lang, "help.access"),
                t(lang, "help.requests"),
            ]
        )

    if can_manage_access:
        lines.extend(
            [
                t(lang, "help.grant_manager"),
                t(lang, "help.revoke_access"),
            ]
        )

    if is_superadmin:
        lines.extend(
            [
                "",
                t(lang, "help.superadmin"),
                t(lang, "help.transfer_owner"),
            ]
        )

    return "\n".join(lines)


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return

    await sync_user_command_menu(bot, message.from_user.id)
    has_clan_access, can_review_requests, can_manage_access, is_superadmin, current_lang = await resolve_command_permissions(message.from_user.id)
    await message.answer(
        build_help_text(
            lang=current_lang or lang,
            has_clan_access=has_clan_access,
            can_review_requests=can_review_requests,
            can_manage_access=can_manage_access,
            is_superadmin=is_superadmin,
        )
    )
