from datetime import UTC, datetime

from app.integrations.telegram.player_cards import format_profile_section


def _profile(*, league_name: str | None, raw_payload: dict | None):
    return type(
        "Profile",
        (),
        {
            "league_name": league_name,
            "exp_level": 200,
            "town_hall_level": 16,
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

    lines = format_profile_section(profile, is_stale=False)

    assert "Лига: Без текущей, лучшая Champion League" in lines


def test_profile_section_prioritizes_league_tier_from_raw_payload() -> None:
    profile = _profile(
        league_name="Titan League I",
        raw_payload={"leagueTier": {"name": "Witch League 17"}},
    )

    lines = format_profile_section(profile, is_stale=False)

    assert "Лига: Witch League 17" in lines


def test_profile_section_shows_no_league_explicitly() -> None:
    profile = _profile(
        league_name=None,
        raw_payload={},
    )

    lines = format_profile_section(profile, is_stale=False)

    assert "Лига: Без лиги" in lines
