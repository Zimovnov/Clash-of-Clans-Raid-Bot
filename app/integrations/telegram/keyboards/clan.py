from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def clan_card_keyboard(tag: str, show_requests: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Последний отчёт", callback_data=f"report_latest:{tag}")
    kb.button(text="Построить отчёт", callback_data=f"report_build:{tag}")
    kb.button(text="Состав", callback_data=f"clan_members:{tag}")
    kb.button(text="Права доступа", callback_data=f"clan_roles:{tag}")
    if show_requests:
        kb.button(text="Доступ к боту", callback_data=f"access_requests:{tag}")
        kb.adjust(2, 2, 1)
        return kb.as_markup()
    kb.adjust(2, 2)
    return kb.as_markup()


def clans_keyboard(tags: list[tuple[str, str]], prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for clan_tag, clan_name in tags:
        kb.button(text=f"{clan_name} ({clan_tag})", callback_data=f"{prefix}:{clan_tag}")
    kb.adjust(1)
    return kb.as_markup()


def clan_members_keyboard(
    tag: str,
    players: list[tuple[str, str]],
    page: int,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    row_sizes: list[int] = []

    for player_tag, label in players:
        kb.button(text=label, callback_data=f"clan_member_open:{tag}:{page}:{player_tag}")
        row_sizes.append(1)

    nav_count = 0
    if has_prev:
        kb.button(text="<", callback_data=f"clan_members_page:{tag}:{page - 1}")
        nav_count += 1
    if has_next:
        kb.button(text=">", callback_data=f"clan_members_page:{tag}:{page + 1}")
        nav_count += 1
    if nav_count:
        row_sizes.append(nav_count)

    kb.button(text="К клану", callback_data=f"clan_open:{tag}")
    row_sizes.append(1)

    kb.adjust(*row_sizes)
    return kb.as_markup()


def report_sections_keyboard(tag: str, report_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="На кик", callback_data=f"report_cat:{tag}:{report_id}:kick:1")
    kb.button(text="Под вопросом", callback_data=f"report_cat:{tag}:{report_id}:questionable:1")
    kb.button(text="Новички", callback_data=f"report_cat:{tag}:{report_id}:newbie:1")
    kb.button(text="Покинули клан", callback_data=f"report_cat:{tag}:{report_id}:left_clan:1")
    kb.button(text="Обновить", callback_data=f"report_build:{tag}")
    kb.button(text="Назад", callback_data=f"clan_open:{tag}")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def report_players_keyboard(
    tag: str,
    report_id: int,
    category: str,
    players: list[tuple[int, str, int]],
    page: int,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row_id, player_name, attacks in players:
        kb.button(
            text=f"{player_name} ({attacks})",
            callback_data=f"report_player:{tag}:{report_id}:{category}:{page}:{row_id}",
        )

    if has_prev:
        kb.button(text="<", callback_data=f"report_cat:{tag}:{report_id}:{category}:{page - 1}")
    if has_next:
        kb.button(text=">", callback_data=f"report_cat:{tag}:{report_id}:{category}:{page + 1}")

    kb.button(text="Назад к отчёту", callback_data=f"report_latest:{tag}")
    kb.adjust(1)
    return kb.as_markup()


def player_card_keyboard(tag: str, report_id: int, category: str, page: int, row_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить профиль", callback_data=f"report_player_refresh:{tag}:{report_id}:{category}:{page}:{row_id}")
    kb.button(text="Назад к списку", callback_data=f"report_cat:{tag}:{report_id}:{category}:{page}")
    kb.button(text="Назад к отчёту", callback_data=f"report_latest:{tag}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def clan_member_card_keyboard(tag: str, page: int, player_tag: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить профиль", callback_data=f"clan_member_refresh:{tag}:{page}:{player_tag}")
    kb.button(text="Назад к составу", callback_data=f"clan_members_page:{tag}:{page}")
    kb.button(text="К клану", callback_data=f"clan_open:{tag}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def access_request_review_keyboard(tag: str, request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Назначить manager", callback_data=f"access_request_approve:{request_id}")
    kb.button(text="Отклонить", callback_data=f"access_request_reject:{request_id}")
    kb.button(text="Назад к запросам", callback_data=f"access_requests:{tag}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def access_requests_list_keyboard(tag: str, requests: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for request_id, label in requests:
        kb.button(text=label, callback_data=f"access_request_open:{tag}:{request_id}")
    kb.button(text="Назад", callback_data=f"clan_open:{tag}")
    kb.adjust(1)
    return kb.as_markup()


def access_request_resolved_keyboard(tag: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="К запросам", callback_data=f"access_requests:{tag}")
    kb.button(text="К клану", callback_data=f"clan_open:{tag}")
    kb.adjust(1, 1)
    return kb.as_markup()
