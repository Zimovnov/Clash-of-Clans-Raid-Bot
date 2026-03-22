from __future__ import annotations

from math import ceil

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.core.dates import format_datetime_human
from app.core.i18n import category_label, t
from app.core.tags import TagNormalizationError, normalize_tag
from app.db.models import ReportCategory, ReportSource
from app.db.repositories import ClanRepository, PlayerRepository, ReportRepository
from app.db.session import AsyncSessionFactory
from app.integrations.clash.client import (
    ClashApiClient,
    ClashApiError,
    ClashApiForbidden,
    ClashApiRateLimited,
    ClashApiUnavailable,
)
from app.integrations.telegram.helpers import ensure_user_access, telegram_identity
from app.integrations.telegram.keyboards.clan import (
    clans_keyboard,
    player_card_keyboard,
    report_players_keyboard,
    report_sections_keyboard,
)
from app.integrations.telegram.player_cards import build_report_player_card_text
from app.services.clan_service import ClanService
from app.services.player_profile_service import PlayerProfileService
from app.services.report_builder import ReportBuilderService, ReportBuildError

router = Router(name="reports")
PAGE_SIZE = 10


def _build_report_error_text(exc: Exception, lang: str) -> str:
    if isinstance(exc, ClashApiForbidden):
        return t(lang, "report.error.forbidden")
    if isinstance(exc, ClashApiRateLimited):
        return t(lang, "report.error.rate_limited")
    if isinstance(exc, ClashApiUnavailable):
        return t(lang, "report.error.unavailable")
    if isinstance(exc, ClashApiError):
        return t(lang, "report.error.clash", reason=exc)
    return t(lang, "report.error.generic", reason=exc)


def _report_summary_text(report, lang: str) -> str:
    period = t(lang, "report.period_unknown")
    if report.raid_weekend_start_at and report.raid_weekend_end_at:
        period = f"{format_datetime_human(report.raid_weekend_start_at)} - {format_datetime_human(report.raid_weekend_end_at)}"
    return t(
        lang,
        "report.summary",
        name=report.clan.name,
        tag=report.clan.tag,
        period=period,
        generated=format_datetime_human(report.generated_at),
        kick=report.kick_count,
        questionable=report.question_count,
        newbies=report.newbie_count,
        left=report.left_count,
    )


@router.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject, lang: str) -> None:
    if message.from_user is None:
        return

    async with AsyncSessionFactory() as session:
        clan_service = ClanService(session, ClashApiClient())
        clans = await clan_service.list_user_clans(telegram_identity(message.from_user))

        if not clans:
            await message.answer(t(lang, "report.no_clans"))
            return

        if command.args:
            raw_tag = command.args.strip()
            selected = None
            try:
                normalized = normalize_tag(raw_tag)
            except TagNormalizationError:
                await message.answer(t(lang, "general.invalid_tag"))
                return
            for clan in clans:
                if clan.tag == normalized:
                    selected = clan
                    break
            if selected is None:
                await message.answer(t(lang, "report.no_access_clan"))
                return

            builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
            try:
                result = await builder.build_report_for_clan(selected.tag, ReportSource.MANUAL)
            except (ReportBuildError, ClashApiError) as exc:
                await message.answer(_build_report_error_text(exc, lang))
                return
            report = await ReportRepository(session).get_by_id(result.report.id)
            if report is None:
                await message.answer(t(lang, "report.built_missing"))
                return
            await message.answer(_report_summary_text(report, lang), reply_markup=report_sections_keyboard(selected.tag, report.id, lang))
            return

        if len(clans) == 1:
            clan = clans[0]
            builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
            try:
                result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL)
            except (ReportBuildError, ClashApiError) as exc:
                await message.answer(_build_report_error_text(exc, lang))
                return
            report = await ReportRepository(session).get_by_id(result.report.id)
            if report is None:
                await message.answer(t(lang, "report.built_missing"))
                return
            await message.answer(_report_summary_text(report, lang), reply_markup=report_sections_keyboard(clan.tag, report.id, lang))
            return

        kb = clans_keyboard([(clan.tag, clan.name) for clan in clans], prefix="report_pick")
        await message.answer(t(lang, "report.pick_clan"), reply_markup=kb)


@router.callback_query(F.data.startswith("report_pick:"))
async def cb_report_pick(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans_repo = ClanRepository(session)
        clan = await clans_repo.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return
        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
        try:
            result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL)
        except (ReportBuildError, ClashApiError) as exc:
            await callback.answer(_build_report_error_text(exc, lang), show_alert=True)
            return

        report = await ReportRepository(session).get_by_id(result.report.id)
        if report is None:
            await callback.answer(t(lang, "general.report_not_found"), show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report, lang), reply_markup=report_sections_keyboard(clan.tag, report.id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("report_latest:"))
async def cb_report_latest(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        report = await reports.latest_for_clan(clan.id)
        if report is None:
            await callback.answer(t(lang, "general.reports_none"), show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report, lang), reply_markup=report_sections_keyboard(clan.tag, report.id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("report_build:"))
async def cb_report_build(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer(t(lang, "general.invalid_tag"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
        try:
            result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL, force_rebuild=True)
        except (ReportBuildError, ClashApiError) as exc:
            await callback.answer(_build_report_error_text(exc, lang), show_alert=True)
            return

        report = await ReportRepository(session).get_by_id(result.report.id)
        if report is None:
            await callback.answer(t(lang, "general.report_not_found"), show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report, lang), reply_markup=report_sections_keyboard(clan.tag, report.id, lang))
    await callback.answer(t(lang, "report.updated"))


@router.callback_query(F.data.startswith("report_cat:"))
async def cb_report_category(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        category = ReportCategory(category_raw)
    except Exception:
        await callback.answer(t(lang, "general.invalid_parameters"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer(t(lang, "general.report_not_found"), show_alert=True)
            return

    rows = [row for row in report.players if row.category == category]
    total = len(rows)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_rows = rows[start:end]
    has_prev = page > 1
    has_next = end < total

    players_data = [(row.id, row.player_name, row.attacks_used) for row in page_rows]
    total_pages = max(1, ceil(total / PAGE_SIZE))

    text_lines = [
        f"{report.clan.name} ({report.clan.tag})",
        t(lang, "report.section", value=category_label(lang, category)),
        t(lang, "report.page", page=page, total_pages=total_pages),
        t(lang, "report.players", count=total),
    ]

    if not page_rows:
        text_lines.append(t(lang, "report.empty"))

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=report_players_keyboard(
            tag=clan_tag,
            report_id=report.id,
            category=category.value,
            players=players_data,
            page=page,
            has_prev=has_prev,
            has_next=has_next,
            lang=lang,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_player:"))
async def cb_report_player(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw, row_id_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        row_id = int(row_id_raw)
    except Exception:
        await callback.answer(t(lang, "general.invalid_parameters"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        players = PlayerRepository(session)
        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())

        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer(t(lang, "general.report_not_found"), show_alert=True)
            return

        row = next((item for item in report.players if item.id == row_id), None)
        if row is None:
            await callback.answer(t(lang, "general.player_not_found"), show_alert=True)
            return

        player_state = await players.get_state_by_player_tag(clan_id=clan.id, player_tag=row.player_tag)
        player = await players.get_by_tag(row.player_tag)
        profile_result = None
        if player is not None:
            try:
                profile_result = await profiles.get_for_player(player, refresh_if_missing=True, force_refresh=False)
            except ClashApiError:
                profile_result = None

    manager_note = player_state.manager_note if player_state is not None else None
    profile = profile_result.profile if profile_result is not None else None
    is_profile_stale = PlayerProfileService.is_stale(profile)
    text = build_report_player_card_text(row, manager_note, profile, is_profile_stale=is_profile_stale, lang=lang)

    await callback.message.edit_text(
        text,
        reply_markup=player_card_keyboard(clan_tag, report_id, category_raw, page, row_id, lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_player_refresh:"))
async def cb_report_player_refresh(callback: CallbackQuery, lang: str) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer(t(lang, "general.invalid_data_format"), show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw, row_id_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        row_id = int(row_id_raw)
    except Exception:
        await callback.answer(t(lang, "general.invalid_parameters"), show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        players = PlayerRepository(session)
        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())

        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer(t(lang, "general.clan_not_found"), show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer(t(lang, "general.no_access"), show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer(t(lang, "general.report_not_found"), show_alert=True)
            return

        row = next((item for item in report.players if item.id == row_id), None)
        if row is None:
            await callback.answer(t(lang, "general.player_not_found"), show_alert=True)
            return

        player_state = await players.get_state_by_player_tag(clan_id=clan.id, player_tag=row.player_tag)
        player = await players.get_by_tag(row.player_tag)
        if player is None:
            await callback.answer(t(lang, "general.profile_unavailable"), show_alert=True)
            return

        try:
            profile_result = await profiles.get_for_player(player, refresh_if_missing=True, force_refresh=True)
        except ClashApiError as exc:
            await callback.answer(_build_report_error_text(exc, lang), show_alert=True)
            return

    manager_note = player_state.manager_note if player_state is not None else None
    profile = profile_result.profile
    is_profile_stale = PlayerProfileService.is_stale(profile)
    text = build_report_player_card_text(row, manager_note, profile, is_profile_stale=is_profile_stale, lang=lang)

    await callback.message.edit_text(
        text,
        reply_markup=player_card_keyboard(clan_tag, report_id, category_raw, page, row_id, lang),
        parse_mode="HTML",
    )
    await callback.answer(t(lang, "profile.refreshed"))
