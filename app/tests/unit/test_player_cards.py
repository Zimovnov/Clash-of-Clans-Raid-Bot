from datetime import UTC, datetime

from app.integrations.telegram.player_cards import build_clan_member_card_text, format_profile_section


def _profile(*, league_name: str | None, raw_payload: dict | None):
    return type(
        "Profile",
        (),
        {
            "league_name": league_name,
            "exp_level": 200,
            "town_hall_level": 16,
            "builder_hall_level": 10,
            "clan_role": "member",
            "refreshed_at": datetime.now(UTC),
            "raw_payload": raw_payload,
        },
    )()


def test_profile_section_uses_best_league_when_current_league_missing() -> None:
    profile = _profile(
        league_name=None,
        raw_payload={"bestLeague": {"name": "Champion League"}},
    )

    lines = format_profile_section(profile, is_stale=False, lang="ru")

    assert "Лига / Без текущей, лучшая Champion League" in lines


def test_profile_section_prioritizes_league_tier_from_raw_payload() -> None:
    profile = _profile(
        league_name="Titan League I",
        raw_payload={"leagueTier": {"name": "Witch League 17"}},
    )

    lines = format_profile_section(profile, is_stale=False, lang="ru")

    assert "Лига / Witch League 17" in lines


def test_profile_section_shows_no_league_explicitly() -> None:
    profile = _profile(
        league_name=None,
        raw_payload={},
    )

    lines = format_profile_section(profile, is_stale=False, lang="ru")

    assert "Лига / Без лиги" in lines


def test_clan_member_card_starts_with_profiler_title() -> None:
    player = type("Player", (), {"name": "Tester", "tag": "#P1"})()
    state = type(
        "State",
        (),
        {
            "player": player,
            "is_current_member": True,
            "first_seen_in_clan_at": datetime.now(UTC),
            "last_seen_in_clan_at": datetime.now(UTC),
        },
    )()

    text = build_clan_member_card_text(state, None, None, is_profile_stale=False, lang="ru")

    assert text.startswith("<b>Profiler App</b>\n")


def test_clan_member_card_uses_slash_for_regular_fields_and_moves_dates_to_bottom() -> None:
    player = type("Player", (), {"name": "KingTrovel", "tag": "#P1"})()
    profile = _profile(league_name="Witch League 17", raw_payload={})
    state = type(
        "State",
        (),
        {
            "player": player,
            "is_current_member": True,
            "first_seen_in_clan_at": datetime.now(UTC),
            "last_seen_in_clan_at": datetime.now(UTC),
        },
    )()

    text = build_clan_member_card_text(state, "Test note", profile, is_profile_stale=False, lang="ru")
    lines = text.splitlines()

    assert "Ник / KingTrovel" in lines
    assert "Тег / #P1" in lines
    assert "Примечание / Test note" in lines

    first_seen_index = next(i for i, line in enumerate(lines) if line.startswith("Первое обнаружение в клане:"))
    last_seen_index = next(i for i, line in enumerate(lines) if line.startswith("Последнее обнаружение:"))
    updated_index = next(i for i, line in enumerate(lines) if line.startswith("Обновлён:"))

    assert first_seen_index > lines.index("Роль в клане / member")
    assert last_seen_index > first_seen_index
    assert updated_index > last_seen_index
