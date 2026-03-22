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
    text = build_help_text(
        lang="en",
        has_clan_access=False,
        can_review_requests=False,
        can_manage_access=False,
        is_superadmin=False,
    )

    assert "/report <TAG>" in text
    assert "/clan <TAG>" not in text
    assert "/roles <TAG>" not in text
    assert "/note <CLAN_TAG> <PLAYER_TAG> <TEXT>" not in text
    assert "/leave_access <TAG>" not in text
    assert "/requests <TAG>" not in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" not in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" not in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" not in text


def test_help_for_owner_shows_access_management_without_superadmin_command() -> None:
    text = build_help_text(
        lang="en",
        has_clan_access=True,
        can_review_requests=True,
        can_manage_access=True,
        is_superadmin=False,
    )

    assert "/clan <TAG>" not in text
    assert "/roles <TAG>" in text
    assert "/note <CLAN_TAG> <PLAYER_TAG> <TEXT>" in text
    assert "/leave_access <TAG>" in text
    assert "/requests <TAG>" in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" not in text


def test_help_for_superadmin_shows_all_admin_commands() -> None:
    text = build_help_text(
        lang="en",
        has_clan_access=True,
        can_review_requests=True,
        can_manage_access=True,
        is_superadmin=True,
    )

    assert "/clan <TAG>" not in text
    assert "/note <CLAN_TAG> <PLAYER_TAG> <TEXT>" in text
    assert "/leave_access <TAG>" in text
    assert "/requests <TAG>" in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" in text
    assert "/transfer_owner <CLAN_TAG> <TELEGRAM_ID>" in text


def test_help_for_ownerless_manager_shows_requests_without_grant_revoke() -> None:
    text = build_help_text(
        lang="en",
        has_clan_access=True,
        can_review_requests=True,
        can_manage_access=False,
        is_superadmin=False,
    )

    assert "/requests <TAG>" in text
    assert "/grant_manager <CLAN_TAG> <TELEGRAM_ID>" not in text
    assert "/revoke_access <CLAN_TAG> <TELEGRAM_ID>" not in text


def test_clan_card_keyboard_buttons_match_access_level() -> None:
    regular = clan_card_keyboard("#TAG", lang="en", show_requests=False)
    privileged = clan_card_keyboard("#TAG", lang="en", show_requests=True)

    assert _button_texts(regular) == ["Latest report", "Build report", "Members", "Access roles"]
    assert _button_texts(privileged) == [
        "Latest report",
        "Build report",
        "Members",
        "Access roles",
        "Bot access",
    ]


def test_player_card_keyboard_contains_refresh_button() -> None:
    markup = player_card_keyboard("#TAG", 42, "kick", 2, 7, "en")
    assert _button_texts(markup) == ["Refresh profile", "Back to list", "Back to report"]


def test_clan_members_keyboard_contains_navigation_and_player_buttons() -> None:
    markup = clan_members_keyboard(
        tag="#TAG",
        players=[("#AAA", "Player 1"), ("#BBB", "Player 2")],
        page=2,
        has_prev=True,
        has_next=True,
        lang="en",
    )

    assert _button_texts(markup) == ["Player 1", "Player 2", "<", ">", "Back to clan"]


def test_clan_member_card_keyboard_contains_refresh_button() -> None:
    markup = clan_member_card_keyboard("#TAG", 2, "#PLAYER", "en")
    assert _button_texts(markup) == ["Refresh profile", "Back to members", "Back to clan"]


def test_all_inline_keyboards_use_handled_callback_prefixes() -> None:
    markups = [
        clan_card_keyboard("#TAG", lang="en", show_requests=True),
        clan_members_keyboard(
            tag="#TAG",
            players=[("#AAA", "Player 1")],
            page=2,
            has_prev=True,
            has_next=True,
            lang="en",
        ),
        clan_member_card_keyboard("#TAG", 2, "#PLAYER", "en"),
        report_sections_keyboard("#TAG", 42, "en"),
        report_players_keyboard(
            tag="#TAG",
            report_id=42,
            category="kick",
            players=[(1, "Player", 0)],
            page=2,
            has_prev=True,
            has_next=True,
            lang="en",
        ),
        player_card_keyboard("#TAG", 42, "kick", 2, 7, "en"),
        access_request_review_keyboard("#TAG", 7, "en"),
        access_requests_list_keyboard("#TAG", [(7, "User | @user")], "en"),
        access_request_resolved_keyboard("#TAG", "en"),
    ]

    callbacks = [callback for markup in markups for callback in _callback_data(markup)]
    prefixes = {callback.split(":", maxsplit=1)[0] for callback in callbacks}

    assert prefixes == HANDLED_CALLBACK_PREFIXES
