from app.integrations.telegram.command_menu import build_command_menu


def _commands(items) -> list[str]:
    return [item.command for item in items]


def test_default_command_menu_contains_base_commands_only() -> None:
    commands = _commands(
        build_command_menu(
            lang="en",
            has_clan_access=False,
            can_review_requests=False,
            can_manage_access=False,
            is_superadmin=False,
        )
    )

    assert commands == ["start", "help", "english", "russian", "addclan", "myclans", "report"]


def test_manager_command_menu_contains_note_and_roles() -> None:
    commands = _commands(
        build_command_menu(
            lang="en",
            has_clan_access=True,
            can_review_requests=False,
            can_manage_access=False,
            is_superadmin=False,
        )
    )

    assert "roles" in commands
    assert "note" in commands
    assert "leave_access" in commands
    assert "requests" not in commands
    assert "transfer_owner" not in commands


def test_ownerless_manager_command_menu_contains_requests_only() -> None:
    commands = _commands(
        build_command_menu(
            lang="en",
            has_clan_access=True,
            can_review_requests=True,
            can_manage_access=False,
            is_superadmin=False,
        )
    )

    assert "requests" in commands
    assert "grant_manager" not in commands
    assert "revoke_access" not in commands


def test_superadmin_command_menu_contains_all_commands() -> None:
    commands = _commands(
        build_command_menu(
            lang="en",
            has_clan_access=True,
            can_review_requests=True,
            can_manage_access=True,
            is_superadmin=True,
        )
    )

    assert "note" in commands
    assert "leave_access" in commands
    assert "requests" in commands
    assert "grant_manager" in commands
    assert "revoke_access" in commands
    assert "transfer_owner" in commands
