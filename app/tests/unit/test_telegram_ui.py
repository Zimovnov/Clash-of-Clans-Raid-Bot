from app.integrations.telegram.handlers.common import build_help_text
from app.integrations.telegram.keyboards.clan import (
    access_request_resolved_keyboard,
    access_request_review_keyboard,
    access_requests_list_keyboard,
    clan_card_keyboard,
    clan_member_card_keyboard,
    clan_members_keyboard,
    player_card_keyboard,
    report_players_keyboard,
    report_sections_keyboard,
)


HANDLED_CALLBACK_PREFIXES = {
    "access_request_approve",
    "access_request_open",
    "access_request_reject",
    "access_requests",
    "clan_member_open",
    "clan_member_refresh",
    "clan_members",
    "clan_members_page",
    "clan_open",
    "clan_roles",
    "report_build",
    "report_cat",
    "report_latest",
    "report_player",
    "report_player_refresh",
}


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_help_for_regular_user_hides_admin_commands() -> None:
    text = build_help_text(has_clan_access=False, can_manage_access=False, is_superadmin=False)

    assert "/report [TAG]" in text
    assert "/roles <TAG>" not in text
    assert "/note <CLAN_TAG> <PLAYER_TAG> <ТЕКСТ>" not in text
    assert "/requests <TAG>" not in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" not in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" not in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" not in text


def test_help_for_owner_shows_access_management_without_superadmin_command() -> None:
    text = build_help_text(has_clan_access=True, can_manage_access=True, is_superadmin=False)

    assert "/roles <TAG>" in text
    assert "/note <CLAN_TAG> <PLAYER_TAG> <ТЕКСТ>" in text
    assert "/requests <TAG>" in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" not in text


def test_help_for_superadmin_shows_all_admin_commands() -> None:
    text = build_help_text(has_clan_access=True, can_manage_access=True, is_superadmin=True)

    assert "/note <CLAN_TAG> <PLAYER_TAG> <ТЕКСТ>" in text
    assert "/requests <TAG>" in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" in text


def test_clan_card_keyboard_buttons_match_access_level() -> None:
    regular = clan_card_keyboard("#TAG", show_requests=False)
    privileged = clan_card_keyboard("#TAG", show_requests=True)

    assert _button_texts(regular) == ["Последний отчёт", "Построить отчёт", "Состав", "Права доступа"]
    assert _button_texts(privileged) == [
        "Последний отчёт",
        "Построить отчёт",
        "Состав",
        "Права доступа",
        "Доступ к боту",
    ]


def test_player_card_keyboard_contains_refresh_button() -> None:
    markup = player_card_keyboard("#TAG", 42, "kick", 2, 7)
    assert _button_texts(markup) == ["Обновить профиль", "Назад к списку", "Назад к отчёту"]


def test_clan_members_keyboard_contains_navigation_and_player_buttons() -> None:
    markup = clan_members_keyboard(
        tag="#TAG",
        players=[("#AAA", "Player 1"), ("#BBB", "Player 2")],
        page=2,
        has_prev=True,
        has_next=True,
    )

    assert _button_texts(markup) == ["Player 1", "Player 2", "<", ">", "К клану"]


def test_clan_member_card_keyboard_contains_refresh_button() -> None:
    markup = clan_member_card_keyboard("#TAG", 2, "#PLAYER")
    assert _button_texts(markup) == ["Обновить профиль", "Назад к составу", "К клану"]


def test_all_inline_keyboards_use_handled_callback_prefixes() -> None:
    markups = [
        clan_card_keyboard("#TAG", show_requests=True),
        clan_members_keyboard(
            tag="#TAG",
            players=[("#AAA", "Player 1")],
            page=2,
            has_prev=True,
            has_next=True,
        ),
        clan_member_card_keyboard("#TAG", 2, "#PLAYER"),
        report_sections_keyboard("#TAG", 42),
        report_players_keyboard(
            tag="#TAG",
            report_id=42,
            category="kick",
            players=[(1, "Player", 0)],
            page=2,
            has_prev=True,
            has_next=True,
        ),
        player_card_keyboard("#TAG", 42, "kick", 2, 7),
        access_request_review_keyboard("#TAG", 7),
        access_requests_list_keyboard("#TAG", [(7, "User | @user")]),
        access_request_resolved_keyboard("#TAG"),
    ]

    callbacks = [callback for markup in markups for callback in _callback_data(markup)]
    prefixes = {callback.split(":", maxsplit=1)[0] for callback in callbacks}

    assert prefixes == HANDLED_CALLBACK_PREFIXES
