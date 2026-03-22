from __future__ import annotations

from math import ceil

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.core.dates import format_datetime_human
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


def _build_report_error_text(exc: Exception) -> str:
    if isinstance(exc, ClashApiForbidden):
        return (
            "Clash API отклонил запрос (403).\n"
            "Скорее всего, в Supercell Developer Portal указан старый IP-адрес или токен уже неактуален."
        )
    if isinstance(exc, ClashApiRateLimited):
        return "Clash API временно ограничил запросы (429). Попробуйте ещё раз чуть позже."
    if isinstance(exc, ClashApiUnavailable):
        return "Clash API временно недоступен. Попробуйте ещё раз чуть позже."
    if isinstance(exc, ClashApiError):
        return f"Ошибка Clash API: {exc}"
    return f"Не удалось построить отчёт: {exc}"


def _report_summary_text(report) -> str:
    period = "не определён"
    if report.raid_weekend_start_at and report.raid_weekend_end_at:
        period = f"{format_datetime_human(report.raid_weekend_start_at)} - {format_datetime_human(report.raid_weekend_end_at)}"
    return (
        f"Отчёт: {report.clan.name} ({report.clan.tag})\n"
        f"Период рейда: {period}\n"
        f"Сгенерирован: {format_datetime_human(report.generated_at)}\n\n"
        f"На кик: {report.kick_count}\n"
        f"Под вопросом: {report.question_count}\n"
        f"Новички: {report.newbie_count}\n"
        f"Покинули клан: {report.left_count}"
    )


@router.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return

    async with AsyncSessionFactory() as session:
        clan_service = ClanService(session, ClashApiClient())
        clans = await clan_service.list_user_clans(telegram_identity(message.from_user))

        if not clans:
            await message.answer("У вас нет доступных кланов")
            return

        if command.args:
            raw_tag = command.args.strip()
            selected = None
            try:
                normalized = normalize_tag(raw_tag)
            except TagNormalizationError:
                await message.answer("Некорректный тег")
                return
            for clan in clans:
                if clan.tag == normalized:
                    selected = clan
                    break
            if selected is None:
                await message.answer("У вас нет доступа к этому клану")
                return

            builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
            try:
                result = await builder.build_report_for_clan(selected.tag, ReportSource.MANUAL)
            except (ReportBuildError, ClashApiError) as exc:
                await message.answer(_build_report_error_text(exc))
                return
            report = await ReportRepository(session).get_by_id(result.report.id)
            if report is None:
                await message.answer("Отчёт построен, но не найден при чтении")
                return
            await message.answer(_report_summary_text(report), reply_markup=report_sections_keyboard(selected.tag, report.id))
            return

        if len(clans) == 1:
            clan = clans[0]
            builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
            try:
                result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL)
            except (ReportBuildError, ClashApiError) as exc:
                await message.answer(_build_report_error_text(exc))
                return
            report = await ReportRepository(session).get_by_id(result.report.id)
            if report is None:
                await message.answer("Отчёт построен, но не найден при чтении")
                return
            await message.answer(_report_summary_text(report), reply_markup=report_sections_keyboard(clan.tag, report.id))
            return

        kb = clans_keyboard([(clan.tag, clan.name) for clan in clans], prefix="report_pick")
        await message.answer("Выберите клан для отчёта:", reply_markup=kb)


@router.callback_query(F.data.startswith("report_pick:"))
async def cb_report_pick(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer("Некорректный тег", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans_repo = ClanRepository(session)
        clan = await clans_repo.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return
        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
        try:
            result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL)
        except (ReportBuildError, ClashApiError) as exc:
            await callback.answer(_build_report_error_text(exc), show_alert=True)
            return

        report = await ReportRepository(session).get_by_id(result.report.id)
        if report is None:
            await callback.answer("Отчёт не найден", show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report), reply_markup=report_sections_keyboard(clan.tag, report.id))
    await callback.answer()


@router.callback_query(F.data.startswith("report_latest:"))
async def cb_report_latest(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer("Некорректный тег", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        report = await reports.latest_for_clan(clan.id)
        if report is None:
            await callback.answer("Отчётов пока нет", show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report), reply_markup=report_sections_keyboard(clan.tag, report.id))
    await callback.answer()


@router.callback_query(F.data.startswith("report_build:"))
async def cb_report_build(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return
    _, raw_tag = callback.data.split(":", maxsplit=1)

    try:
        clan_tag = normalize_tag(raw_tag)
    except TagNormalizationError:
        await callback.answer("Некорректный тег", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        builder = ReportBuilderService(session=session, clash_client=ClashApiClient())
        try:
            result = await builder.build_report_for_clan(clan.tag, ReportSource.MANUAL, force_rebuild=True)
        except (ReportBuildError, ClashApiError) as exc:
            await callback.answer(_build_report_error_text(exc), show_alert=True)
            return

        report = await ReportRepository(session).get_by_id(result.report.id)
        if report is None:
            await callback.answer("Отчёт не найден", show_alert=True)
            return

    await callback.message.edit_text(_report_summary_text(report), reply_markup=report_sections_keyboard(clan.tag, report.id))
    await callback.answer("Отчёт обновлён")


@router.callback_query(F.data.startswith("report_cat:"))
async def cb_report_category(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Неверный формат данных", show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        category = ReportCategory(category_raw)
    except Exception:
        await callback.answer("Неверные параметры", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer("Отчёт не найден", show_alert=True)
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
        f"Раздел: {category.value}",
        f"Страница {page}/{total_pages}",
        f"Игроков: {total}",
    ]

    if not page_rows:
        text_lines.append("Список пуст")

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
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_player:"))
async def cb_report_player(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer("Неверный формат данных", show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw, row_id_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        row_id = int(row_id_raw)
    except Exception:
        await callback.answer("Неверные параметры", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        players = PlayerRepository(session)
        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())

        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer("Отчёт не найден", show_alert=True)
            return

        row = next((item for item in report.players if item.id == row_id), None)
        if row is None:
            await callback.answer("Игрок не найден", show_alert=True)
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
    text = build_report_player_card_text(row, manager_note, profile, is_profile_stale=is_profile_stale)

    await callback.message.edit_text(
        text,
        reply_markup=player_card_keyboard(clan_tag, report_id, category_raw, page, row_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_player_refresh:"))
async def cb_report_player_refresh(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer("Неверный формат данных", show_alert=True)
        return

    _, raw_tag, report_id_raw, category_raw, page_raw, row_id_raw = parts

    try:
        clan_tag = normalize_tag(raw_tag)
        report_id = int(report_id_raw)
        page = max(1, int(page_raw))
        row_id = int(row_id_raw)
    except Exception:
        await callback.answer("Неверные параметры", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        clans = ClanRepository(session)
        reports = ReportRepository(session)
        players = PlayerRepository(session)
        profiles = PlayerProfileService(session=session, clash_client=ClashApiClient())

        clan = await clans.get_by_tag(clan_tag)
        if clan is None:
            await callback.answer("Клан не найден", show_alert=True)
            return

        access = await ensure_user_access(session, callback.from_user, clan)
        if access is None:
            await callback.answer("Нет доступа", show_alert=True)
            return

        report = await reports.get_by_id(report_id)
        if report is None:
            await callback.answer("Отчёт не найден", show_alert=True)
            return

        row = next((item for item in report.players if item.id == row_id), None)
        if row is None:
            await callback.answer("Игрок не найден", show_alert=True)
            return

        player_state = await players.get_state_by_player_tag(clan_id=clan.id, player_tag=row.player_tag)
        player = await players.get_by_tag(row.player_tag)
        if player is None:
            await callback.answer("Профиль игрока недоступен", show_alert=True)
            return

        try:
            profile_result = await profiles.get_for_player(player, refresh_if_missing=True, force_refresh=True)
        except ClashApiError as exc:
            await callback.answer(_build_report_error_text(exc), show_alert=True)
            return

    manager_note = player_state.manager_note if player_state is not None else None
    profile = profile_result.profile
    is_profile_stale = PlayerProfileService.is_stale(profile)
    text = build_report_player_card_text(row, manager_note, profile, is_profile_stale=is_profile_stale)

    await callback.message.edit_text(
        text,
        reply_markup=player_card_keyboard(clan_tag, report_id, category_raw, page, row_id),
    )
    await callback.answer("Профиль обновлён")
