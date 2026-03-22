from __future__ import annotations

import logging
from math import ceil

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.core.config import get_settings
from app.core.dates import format_datetime_human
from app.core.i18n import request_status_label, t, translate_service_error
from app.core.tags import TagNormalizationError, normalize_tag
from app.db.models import Clan, ClanAccess, ClanAccessRequest, ClanAccessRequestStatus, ClanRole
from app.db.repositories import ClanRepository, PlayerRepository, SnapshotRepository
from app.db.session import AsyncSessionFactory
from app.integrations.clash.client import (
    ClashApiClient,
    ClashApiError,
    ClashApiForbidden,
    ClashApiRateLimited,
    ClashApiUnavailable,
)
from app.integrations.telegram.command_menu import sync_user_command_menu
from app.integrations.telegram.helpers import ensure_user_access, telegram_identity
from app.integrations.telegram.keyboards.clan import (
    access_request_resolved_keyboard,
    access_request_review_keyboard,
    access_requests_list_keyboard,
    clan_card_keyboard,
    clan_member_card_keyboard,
    clan_members_keyboard,
    clans_keyboard,
)
from app.integrations.telegram.player_cards import build_clan_member_card_text
from app.services.clan_service import (
    AddClanResult,
    ClanAccessDeniedError,
    ClanAccessRequestAction,
    ClanAccessRequestAlreadyHandledError,
    ClanAccessRequestNotFoundError,
    ClanPermissionDeniedError,
    ClanService,
    ClanServiceError,
    RoleOverview,
)
from app.services.player_profile_service import PlayerProfileService

logger = logging.getLogger(__name__)
router = Router(name="clans")
CLAN_MEMBERS_PAGE_SIZE = 10


def _usage(lang: str, command: str) -> str:
    return f"{'Usage' if lang == 'en' else 'Использование'}: {command}"


def _build_clan_text(lang: str, name: str, tag: str, status: bool) -> str:
    return t(
        lang,
        "clan.card",
        name=name,
        tag=tag,
        status=t(lang, "clan.status_on") if status else t(lang, "clan.status_off"),
    )


def _is_superadmin(telegram_id: int) -> bool:
    return telegram_id in get_settings().superadmin_telegram_ids


def _format_user(user, lang: str) -> str:
    username = f"@{user.username}" if user.username else "-"
    display_name = user.first_name or user.username or t(lang, "general.none")
    return f"{display_name} | id={user.telegram_id} | {username}"


def _can_manage_requests(access_role: ClanRole | None, is_superadmin: bool, *, has_owner: bool = True) -> bool:
    if is_superadmin or access_role == ClanRole.OWNER:
        return True
    return access_role == ClanRole.MANAGER and not has_owner


def _clan_keyboard(tag: str, access_role: ClanRole | None, is_superadmin: bool, lang: str) -> object:
    return clan_card_keyboard(tag, lang=lang, show_requests=_can_manage_requests(access_role, is_superadmin))


def _build_roles_text(lang: str, overview: RoleOverview) -> str:
    lines = [t(lang, "roles.header", name=overview.clan.name, tag=overview.clan.tag), "", t(lang, "roles.active")]
    for item in overview.accesses:
        lines.append(f"- {item.role.value}: {_format_user(item.user, lang)}")

    if overview.pending_requests:
        lines.extend(["", t(lang, "roles.pending")])
        for request in overview.pending_requests:
            lines.append(f"- {request.requested_role.value}: {_format_user(request.user, lang)}")

    return "\n".join(lines)


def _build_access_requests_text(lang: str, clan: Clan, requests: list[ClanAccessRequest]) -> str:
    lines = [t(lang, "requests.header", name=clan.name, tag=clan.tag, count=len(requests))]
    if not requests:
        lines.extend(["", t(lang, "general.requests_none")])
    return "\n".join(lines)


def _build_access_request_text(lang: str, request: ClanAccessRequest) -> str:
    return t(
        lang,
        "requests.item_title",
        name=request.clan.name,
        tag=request.clan.tag,
        user=_format_user(request.user, lang),
        role=request.requested_role.value,
    )


def _build_ownerless_access_request_text(lang: str, request: ClanAccessRequest) -> str:
    return f"{_build_access_request_text(lang, request)}\n\n{t(lang, 'requests.ownerless_hint')}"


def _build_access_request_resolution_text(lang: str, request: ClanAccessRequest) -> str:
    resolver = _format_user(request.resolved_by_user, lang) if request.resolved_by_user else t(lang, "general.none")
    return t(
        lang,
        "requests.resolution_title",
        name=request.clan.name,
        tag=request.clan.tag,
        user=_format_user(request.user, lang),
        role=request.requested_role.value,
        status=request_status_label(lang, request.status),
        resolver=resolver,
    )


def _request_button_label(lang: str, request: ClanAccessRequest) -> str:
    username = f"@{request.user.username}" if request.user.username else str(request.user.telegram_id)
    fallback = "User" if lang == "en" else "Пользователь"
    return f"{request.user.first_name or request.user.username or fallback} | {username}"


def _current_member_states(latest_snapshot, states):
    if latest_snapshot is None:
        return []

    states_by_tag = {state.player.tag: state for state in states if state.player is not None}
    ordered_states = [states_by_tag[tag] for tag in latest_snapshot.member_tags if tag in states_by_tag]
    return ordered_states


def _member_button_label(state, lang: str) -> str:
    player = state.player
    if player is None:
        return "Player" if lang == "en" else "Игрок"
    return player.name


def _build_member_list_text(lang: str, clan: Clan, latest_snapshot, page: int, total_pages: int, page_states) -> str:
    lines = [
        t(lang, "members.header", name=clan.name, tag=clan.tag),
        t(lang, "members.date", value=format_datetime_human(latest_snapshot.taken_at)),
        t(lang, "members.count", count=latest_snapshot.member_count),
        t(lang, "members.page", page=page, total_pages=total_pages),
    ]

    if page_states:
        lines.extend(["", t(lang, "members.choose")])
    else:
        lines.extend(["", t(lang, "members.empty")])

    return "\n".join(lines)


def _build_profile_error_text(lang: str, exc: ClashApiError) -> str:
    if isinstance(exc, ClashApiForbidden):
        return t(lang, "profile.error.forbidden")
    if isinstance(exc, ClashApiRateLimited):
        return t(lang, "profile.error.rate_limited")
    if isinstance(exc, ClashApiUnavailable):
        return t(lang, "profile.error.unavailable")
    return t(lang, "profile.error.generic", reason=exc)


async def _notify_owners_about_request(bot: Bot, owners: list[ClanAccess], request: ClanAccessRequest) -> None:
    for owner in owners:
        try:
            owner_lang = getattr(owner.user, "language", "en")
            await bot.send_message(
                chat_id=owner.user.telegram_id,
                text=_build_access_request_text(owner_lang, request),
                reply_markup=access_request_review_keyboard(request.clan.tag, request.id, owner_lang),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "access_request_owner_notification_failed",
                extra={"clan_id": request.clan_id, "owner_user_id": owner.user_id, "request_id": request.id},
            )


async def _notify_ownerless_request_reviewers(bot: Bot, managers: list[ClanAccess], request: ClanAccessRequest) -> None:
    delivered_ids: set[int] = set()

    for manager in managers:
        try:
            manager_lang = getattr(manager.user, "language", "en")
            await bot.send_message(
                chat_id=manager.user.telegram_id,
                text=_build_ownerless_access_request_text(manager_lang, request),
                reply_markup=access_request_review_keyboard(request.clan.tag, request.id, manager_lang),
            )
            delivered_ids.add(manager.user.telegram_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "ownerless_access_request_manager_notification_failed",
                extra={"clan_id": request.clan_id, "manager_user_id": manager.user_id, "request_id": request.id},
            )

    for superadmin_id in get_settings().superadmin_telegram_ids:
        if superadmin_id in delivered_ids:
            continue
        try:
            await bot.send_message(
                chat_id=superadmin_id,
                text=_build_ownerless_access_request_text("en", request),
                reply_markup=access_request_review_keyboard(request.clan.tag, request.id, "en"),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "ownerless_access_request_superadmin_notification_failed",
                extra={"clan_id": request.clan_id, "superadmin_telegram_id": superadmin_id, "request_id": request.id},
            )


async def _notify_requester(bot: Bot, request: ClanAccessRequest) -> None:
    requester_lang = getattr(request.user, "language", "en")
    if request.status == ClanAccessRequestStatus.APPROVED:
        text = t(requester_lang, "requests.approved_notify", name=request.clan.name, tag=request.clan.tag)
        reply_markup = clan_card_keyboard(request.clan.tag, requester_lang)
    elif request.status == ClanAccessRequestStatus.REJECTED:
        text = t(requester_lang, "requests.rejected_notify", name=request.clan.name, tag=request.clan.tag)
        reply_markup = None
    else:
        return

    try:
        await bot.send_message(chat_id=request.user.telegram_id, text=text, reply_markup=reply_markup)
        await sync_user_command_menu(bot, request.user.telegram_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "access_request_requester_notification_failed",
            extra={"clan_id": request.clan_id, "request_user_id": request.user_id, "request_id": request.id},
        )


async def _notify_managers_about_owner_exit(bot: Bot, managers: list[ClanAccess], clan: Clan) -> None:
    for manager in managers:
        try:
            manager_lang = getattr(manager.user, "language", "en")
            await bot.send_message(
                chat_id=manager.user.telegram_id,
                text=t(manager_lang, "leave.owner_left_notify", clan_name=clan.name, clan_tag=clan.tag),
                reply_markup=clan_card_keyboard(clan.tag, manager_lang),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "owner_exit_manager_notification_failed",
                extra={"clan_id": clan.id, "manager_user_id": manager.user_id},
            )


async def _load_clan_for_view(session, tg_user, clan_tag: str) -> tuple[Clan | None, ClanRole | None, bool]:
    clan = await ClanRepository(session).get_by_tag(clan_tag)
    if clan is None or tg_user is None:
        return clan, None, False

    is_superadmin = _is_superadmin(tg_user.id)
    if is_superadmin:
        return clan, None, True

    access_ctx = await ensure_user_access(session, tg_user, clan)
    if access_ctx is None:
        return clan, None, False
    return clan, access_ctx.access.role, True


async def _load_clan_for_request_management(session, tg_user, clan_tag: str) -> tuple[Clan | None, ClanRole | None, bool]:
    clan, role, allowed = await _load_clan_for_view(session, tg_user, clan_tag)
    if clan is None or tg_user is None:
        return clan, role, False
    has_owner = bool(await ClanRepository(session).list_accesses_by_role(clan.id, ClanRole.OWNER))
    if _can_manage_requests(role, _is_superadmin(tg_user.id), has_owner=has_owner):
        return clan, role, True
    return clan, role, False


@router.message(Command("addclan"))
async def cmd_add_clan(message: Message, command: CommandObject, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(_usage(lang, "/addclan <TAG>"))
        return

    owners: list[ClanAccess] = []
    managers: list[ClanAccess] = []
    result: AddClanResult | None = None

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            result = await service.add_clan_or_request_access(telegram_identity(message.from_user), command.args.strip())
            if result.action == ClanAccessRequestAction.ACCESS_REQUEST_CREATED:
                owners = await service.list_owners(result.clan.id)
                if not owners:
                    overview = await service.list_roles(result.clan.tag)
                    if overview is not None:
                        managers = [item for item in overview.accesses if item.role == ClanRole.MANAGER]
        except ClanServiceError as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return
        except TagNormalizationError:
            await message.answer(t(lang, "general.invalid_tag"))
            return
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"{t(lang, 'general.error_prefix')}: {exc}")
            return

    if result is None:
        await message.answer(t(lang, "service.no_result"))
        return

    if result.action in {ClanAccessRequestAction.OWNER_ASSIGNED, ClanAccessRequestAction.ACCESS_ALREADY_EXISTS}:
        await sync_user_command_menu(bot, message.from_user.id)
        await message.answer(
            t(lang, "clan.connected", name=result.clan.name, tag=result.clan.tag, role=result.role.value),
            reply_markup=_clan_keyboard(result.clan.tag, result.role, _is_superadmin(message.from_user.id), lang),
        )
        return

    if result.action == ClanAccessRequestAction.ACCESS_REQUEST_PENDING:
        await message.answer(t(lang, "clan.request_pending", name=result.clan.name, tag=result.clan.tag))
        return

    if result.action == ClanAccessRequestAction.ACCESS_REQUEST_CREATED and result.access_request is not None:
        if owners:
            await _notify_owners_about_request(bot, owners, result.access_request)
            await message.answer(t(lang, "clan.request_created", name=result.clan.name, tag=result.clan.tag))
        else:
            await _notify_ownerless_request_reviewers(bot, managers, result.access_request)
            await message.answer(t(lang, "clan.request_created_ownerless", name=result.clan.name, tag=result.clan.tag))
        return

    await message.answer(t(lang, "service.no_result"))


@router.message(Command("myclans"))
async def cmd_myclans(message: Message, lang: str) -> None:
    if message.from_user is None:
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        clans = await service.list_user_clans(telegram_identity(message.from_user))

    if not clans:
        await message.answer(t(lang, "clan.none"))
        return

    text = t(lang, "clan.available", items="\n".join(f"- {clan.name} ({clan.tag})" for clan in clans))
    kb = clans_keyboard([(clan.tag, clan.name) for clan in clans], prefix="clan_open")
    await message.answer(text, reply_markup=kb)


@router.message(Command("clan"))
async def cmd_clan(message: Message, command: CommandObject, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(_usage(lang, "/clan <TAG>"))
        return

    try:
        clan_tag = normalize_tag(command.args.strip())
    except TagNormalizationError:
        await message.answer(t(lang, "general.invalid_tag"))
        return

    async with AsyncSessionFactory() as session:
        clan, access_role, allowed = await _load_clan_for_view(session, message.from_user, clan_tag)
        if clan is None:
            await message.answer(t(lang, "general.clan_not_found"))
            return
        if not allowed:
            await message.answer(t(lang, "clan.access_missing_add"))
            return

        await message.answer(
            _build_clan_text(lang, clan.name, clan.tag, clan.is_tracking),
            reply_markup=_clan_keyboard(clan.tag, access_role, _is_superadmin(message.from_user.id), lang),
        )


@router.message(Command("roles"))
async def cmd_roles(message: Message, command: CommandObject, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(_usage(lang, "/roles <TAG>"))
        return

    try:
        clan_tag = normalize_tag(command.args.strip())
    except TagNormalizationError:
        await message.answer(t(lang, "general.invalid_tag"))
        return

    async with AsyncSessionFactory() as session:
        clan, access_role, allowed = await _load_clan_for_view(session, message.from_user, clan_tag)
        if clan is None:
            await message.answer(t(lang, "general.clan_not_found"))
            return
        if not allowed:
            await message.answer(t(lang, "report.no_access_clan"))
            return

        overview = await ClanService(session=session, clash_client=ClashApiClient()).list_roles(clan.tag)

    if overview is None:
        await message.answer(t(lang, "general.clan_not_found"))
        return

    await message.answer(_build_roles_text(lang, overview), reply_markup=_clan_keyboard(clan.tag, access_role, _is_superadmin(message.from_user.id), lang))


@router.message(Command("requests"))
async def cmd_requests(message: Message, command: CommandObject, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(_usage(lang, "/requests <TAG>"))
        return

    try:
        clan_tag = normalize_tag(command.args.strip())
    except TagNormalizationError:
        await message.answer(t(lang, "general.invalid_tag"))
        return

    async with AsyncSessionFactory() as session:
        clan, _, allowed = await _load_clan_for_request_management(session, message.from_user, clan_tag)
        if clan is None:
            await message.answer(t(lang, "general.clan_not_found"))
            return
        if not allowed:
            await message.answer(t(lang, "requests.section_denied"))
            return

        overview = await ClanService(session=session, clash_client=ClashApiClient()).list_roles(clan.tag)

    if overview is None:
        await message.answer(t(lang, "general.clan_not_found"))
        return

    request_buttons = [(request.id, _request_button_label(lang, request)) for request in overview.pending_requests]
    await message.answer(
        _build_access_requests_text(lang, overview.clan, overview.pending_requests),
        reply_markup=access_requests_list_keyboard(overview.clan.tag, request_buttons, lang),
    )


@router.message(Command("note"))
async def cmd_note(message: Message, command: CommandObject, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(t(lang, "note.usage"))
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer(t(lang, "note.usage"))
        return

    clan_tag, player_tag, raw_note = parts
    note = raw_note.strip()
    normalized_note = None if note == "-" else note
    if normalized_note is not None and len(normalized_note) > 500:
        await message.answer(t(lang, "note.too_long"))
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            result = await service.set_player_note(
                actor_identity=telegram_identity(message.from_user),
                raw_clan_tag=clan_tag,
                raw_player_tag=player_tag,
                note=normalized_note,
                is_superadmin=_is_superadmin(message.from_user.id),
            )
        except (ClanAccessDeniedError, ClanServiceError) as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return

    rendered_note = result.note or "—"
    await message.answer(t(lang, "note.updated", clan_name=result.clan.name, clan_tag=result.clan.tag, player_name=result.player_name, player_tag=result.player_tag, note=rendered_note))


@router.message(Command("leave_access"))
async def cmd_leave_access(message: Message, command: CommandObject, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(t(lang, "leave.usage"))
        return

    managers_to_notify: list[ClanAccess] = []

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            result = await service.leave_access(
                actor_identity=telegram_identity(message.from_user),
                raw_tag=command.args.strip(),
            )
            if result.role == ClanRole.OWNER:
                overview = await service.list_roles(result.clan.tag)
                if overview is not None and not any(item.role == ClanRole.OWNER for item in overview.accesses):
                    managers_to_notify = [item for item in overview.accesses if item.role == ClanRole.MANAGER]
        except ClanServiceError as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return

    await sync_user_command_menu(bot, message.from_user.id)
    text = t(lang, "leave.confirm", clan_name=result.clan.name, clan_tag=result.clan.tag)
    if result.is_unassigned:
        text = f"{text}\n{t(lang, 'leave.unassigned')}"
    await message.answer(text)
    if managers_to_notify:
        await _notify_managers_about_owner_exit(bot, managers_to_notify, result.clan)


@router.message(Command("grant_manager"))
async def cmd_grant_manager(message: Message, command: CommandObject, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(t(lang, "grant.usage"))
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.answer(t(lang, "grant.usage"))
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
            clan, target_user = await service.grant_manager(
                actor_identity=telegram_identity(message.from_user),
                raw_tag=clan_tag,
                telegram_id=telegram_id,
                is_superadmin=_is_superadmin(message.from_user.id),
            )
        except (ClanPermissionDeniedError, ClanServiceError) as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return

    try:
        target_lang = getattr(target_user, "language", "en")
        await bot.send_message(
            chat_id=target_user.telegram_id,
            text=t(target_lang, "grant.notify", clan_name=clan.name, clan_tag=clan.tag),
            reply_markup=clan_card_keyboard(clan.tag, target_lang),
        )
        await sync_user_command_menu(bot, target_user.telegram_id)
    except Exception:  # noqa: BLE001
        logger.exception("grant_manager_notification_failed", extra={"telegram_id": target_user.telegram_id, "clan_id": clan.id})

    await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(t(lang, "grant.confirm", telegram_id=telegram_id, clan_name=clan.name, clan_tag=clan.tag))


@router.message(Command("revoke_access"))
async def cmd_revoke_access(message: Message, command: CommandObject, bot: Bot, lang: str) -> None:
    if message.from_user is None:
        return
    if not command.args:
        await message.answer(t(lang, "revoke.usage"))
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.answer(t(lang, "revoke.usage"))
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
            clan, target_user = await service.revoke_access(
                actor_identity=telegram_identity(message.from_user),
                raw_tag=clan_tag,
                telegram_id=telegram_id,
                is_superadmin=_is_superadmin(message.from_user.id),
            )
        except (ClanPermissionDeniedError, ClanServiceError) as exc:
            await message.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}")
            return

    try:
        target_lang = getattr(target_user, "language", "en")
        await bot.send_message(
            chat_id=target_user.telegram_id,
            text=t(target_lang, "revoke.notify", clan_name=clan.name, clan_tag=clan.tag),
        )
        await sync_user_command_menu(bot, target_user.telegram_id)
    except Exception:  # noqa: BLE001
        logger.exception("revoke_access_notification_failed", extra={"telegram_id": target_user.telegram_id, "clan_id": clan.id})

    await sync_user_command_menu(bot, message.from_user.id)
    await message.answer(t(lang, "revoke.confirm", telegram_id=telegram_id, clan_name=clan.name, clan_tag=clan.tag))


@router.callback_query(F.data.startswith("clan_open:"))
async def cb_clan_open(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    _, raw_tag = callback.data.split(":", maxsplit=1)
    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, access_role, allowed = await _load_clan_for_view(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

    if callback.message is not None:
        await callback.message.edit_text(
            _build_clan_text(lang, clan.name, clan.tag, clan.is_tracking),
            reply_markup=_clan_keyboard(clan.tag, access_role, _is_superadmin(callback.from_user.id), lang),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("clan_roles:"))
async def cb_clan_roles(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)
    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, access_role, allowed = await _load_clan_for_view(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        overview = await ClanService(session=session, clash_client=ClashApiClient()).list_roles(clan.tag)

    if overview is None:
        await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            _build_roles_text(lang, overview),
            reply_markup=_clan_keyboard(clan.tag, access_role, _is_superadmin(callback.from_user.id), lang),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("clan_members:"))
async def cb_clan_members(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)
    await _render_clan_members_page(callback, raw_tag=raw_tag, page=1, lang=lang)


@router.callback_query(F.data.startswith("clan_members_page:"))
async def cb_clan_members_page(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, page_raw = parts
    try:
        page = max(1, int(page_raw))
    except ValueError:
        await callback.answer(t(lang, "general.invalid_page"), show_alert=True)
        return

    await _render_clan_members_page(callback, raw_tag=raw_tag, page=page, lang=lang)


async def _render_clan_members_page(callback: CallbackQuery, *, raw_tag: str, page: int, lang: str) -> None:
    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, access_role, allowed = await _load_clan_for_view(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        latest_snapshot = await SnapshotRepository(session).latest(clan.id)
        states = await PlayerRepository(session).list_states_for_clan(clan.id)

    if latest_snapshot is None:
        text = t(lang, "members.no_data", tag=clan.tag)
        reply_markup = _clan_keyboard(clan.tag, access_role, _is_superadmin(callback.from_user.id), lang)
    else:
        current_states = _current_member_states(latest_snapshot, states)
        total = len(current_states)
        total_pages = max(1, ceil(total / CLAN_MEMBERS_PAGE_SIZE))
        page = min(page, total_pages)
        start = (page - 1) * CLAN_MEMBERS_PAGE_SIZE
        end = start + CLAN_MEMBERS_PAGE_SIZE
        page_states = current_states[start:end]
        text = _build_member_list_text(lang, clan, latest_snapshot, page, total_pages, page_states)
        reply_markup = clan_members_keyboard(
            tag=clan.tag,
            players=[(state.player.tag, _member_button_label(state, lang)) for state in page_states if state.player is not None],
            page=page,
            has_prev=page > 1,
            has_next=end < total,
            lang=lang,
        )

    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("clan_member_open:"))
async def cb_clan_member_open(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, page_raw, raw_player_tag = parts
    try:
        clan_tag = normalize_tag(raw_tag)
        player_tag = normalize_tag(raw_player_tag)
        page = max(1, int(page_raw))
    except (TagNormalizationError, ValueError):
        await callback.answer(t(lang, "general.invalid_parameters"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, _, allowed = await _load_clan_for_view(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        players = PlayerRepository(session)
        state = await players.get_state_by_player_tag(clan.id, player_tag)
        if state is None or state.player is None:
            await callback.answer(t(lang, "general.player_not_found"), show_alert=True)
            return

        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())
        profile_result = None
        profile_error: Exception | None = None
        try:
            profile_result = await profiles.get_for_player(state.player, refresh_if_missing=True, force_refresh=False)
        except ClashApiError as exc:
            profile_error = exc

    profile = profile_result.profile if profile_result is not None else None
    is_profile_stale = PlayerProfileService.is_stale(profile)
    text = build_clan_member_card_text(state, state.manager_note, profile, is_profile_stale=is_profile_stale, lang=lang)

    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=clan_member_card_keyboard(clan.tag, page, state.player.tag, lang),
            parse_mode="HTML",
        )
    if profile_error is not None:
        await callback.answer(_build_profile_error_text(lang, profile_error), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("clan_member_refresh:"))
async def cb_clan_member_refresh(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, page_raw, raw_player_tag = parts
    try:
        clan_tag = normalize_tag(raw_tag)
        player_tag = normalize_tag(raw_player_tag)
        page = max(1, int(page_raw))
    except (TagNormalizationError, ValueError):
        await callback.answer(t(lang, "general.invalid_parameters"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, _, allowed = await _load_clan_for_view(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        players = PlayerRepository(session)
        state = await players.get_state_by_player_tag(clan.id, player_tag)
        if state is None or state.player is None:
            await callback.answer(t(lang, "general.player_not_found"), show_alert=True)
            return

        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())
        try:
            profile_result = await profiles.get_for_player(state.player, refresh_if_missing=True, force_refresh=True)
        except ClashApiError as exc:
            await callback.answer(_build_profile_error_text(lang, exc), show_alert=True)
            return

    profile = profile_result.profile
    is_profile_stale = PlayerProfileService.is_stale(profile)
    text = build_clan_member_card_text(state, state.manager_note, profile, is_profile_stale=is_profile_stale, lang=lang)

    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=clan_member_card_keyboard(clan.tag, page, state.player.tag, lang),
            parse_mode="HTML",
        )
    await callback.answer(t(lang, "profile.refreshed"))


@router.callback_query(F.data.startswith("access_requests:"))
async def cb_access_requests(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)
    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, _, allowed = await _load_clan_for_request_management(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "requests.section_denied"), show_alert=True)
            return

        overview = await ClanService(session=session, clash_client=ClashApiClient()).list_roles(clan.tag)

    if overview is None:
        await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
        return

    request_buttons = [(request.id, _request_button_label(lang, request)) for request in overview.pending_requests]
    if callback.message is not None:
        await callback.message.edit_text(
            _build_access_requests_text(lang, overview.clan, overview.pending_requests),
            reply_markup=access_requests_list_keyboard(overview.clan.tag, request_buttons, lang),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("access_request_open:"))
async def cb_access_request_open(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, request_id_raw = parts
    try:
        clan_tag = normalize_tag(raw_tag)
        request_id = int(request_id_raw)
    except ValueError:
        await callback.answer(t(lang, "general.invalid_request_id"), show_alert=True)
        return
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clan, _, allowed = await _load_clan_for_request_management(session, callback.from_user, clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        if not allowed:
            await callback.answer(t(lang, "requests.section_denied"), show_alert=True)
            return

        service = ClanService(session=session, clash_client=ClashApiClient())
        request = await service.get_access_request(request_id)

    if request is None or request.clan.tag != clan_tag:
        await callback.answer(t(lang, "requests.not_found"), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            _build_access_request_text(lang, request),
            reply_markup=access_request_review_keyboard(request.clan.tag, request.id, lang),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("access_request_approve:"))
async def cb_access_request_approve(callback: CallbackQuery, bot: Bot, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, request_id_raw = callback.data.split(":", maxsplit=1)

    try:
        request_id = int(request_id_raw)
    except ValueError:
        await callback.answer(t(lang, "general.invalid_request_id"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            request = await service.approve_access_request(
                actor_identity=telegram_identity(callback.from_user),
                request_id=request_id,
                is_superadmin=_is_superadmin(callback.from_user.id),
            )
        except ClanAccessRequestNotFoundError:
            await callback.answer(t(lang, "requests.not_found"), show_alert=True)
            return
        except ClanAccessRequestAlreadyHandledError:
            await callback.answer(t(lang, "requests.already_handled"), show_alert=True)
            return
        except ClanPermissionDeniedError:
            await callback.answer(t(lang, "requests.decision_denied"), show_alert=True)
            return
        except ClanServiceError as exc:
            await callback.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}", show_alert=True)
            return

    if callback.message is not None:
        await callback.message.edit_text(
            _build_access_request_resolution_text(lang, request),
            reply_markup=access_request_resolved_keyboard(request.clan.tag, lang),
        )
    await _notify_requester(bot, request)
    await sync_user_command_menu(bot, callback.from_user.id)
    await callback.answer(t(lang, "requests.access_granted"))


@router.callback_query(F.data.startswith("access_request_reject:"))
async def cb_access_request_reject(callback: CallbackQuery, bot: Bot, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, request_id_raw = callback.data.split(":", maxsplit=1)

    try:
        request_id = int(request_id_raw)
    except ValueError:
        await callback.answer(t(lang, "general.invalid_request_id"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        service = ClanService(session=session, clash_client=ClashApiClient())
        try:
            request = await service.reject_access_request(
                actor_identity=telegram_identity(callback.from_user),
                request_id=request_id,
                is_superadmin=_is_superadmin(callback.from_user.id),
            )
        except ClanAccessRequestNotFoundError:
            await callback.answer(t(lang, "requests.not_found"), show_alert=True)
            return
        except ClanAccessRequestAlreadyHandledError:
            await callback.answer(t(lang, "requests.already_handled"), show_alert=True)
            return
        except ClanPermissionDeniedError:
            await callback.answer(t(lang, "requests.decision_denied"), show_alert=True)
            return
        except ClanServiceError as exc:
            await callback.answer(f"{t(lang, 'general.error_prefix')}: {translate_service_error(lang, exc)}", show_alert=True)
            return

    if callback.message is not None:
        await callback.message.edit_text(
            _build_access_request_resolution_text(lang, request),
            reply_markup=access_request_resolved_keyboard(request.clan.tag, lang),
        )
    await _notify_requester(bot, request)
    await sync_user_command_menu(bot, callback.from_user.id)
    await callback.answer(t(lang, "requests.rejected"))
