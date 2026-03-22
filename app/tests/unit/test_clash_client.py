from app.integrations.clash.client import _extract_league_name


def test_extract_league_name_prefers_league_tier() -> None:
    payload = {
        "league": {"name": "Titan League I"},
        "leagueTier": {"name": "Witch League 17"},
    }

    assert _extract_league_name(payload) == "Witch League 17"


def test_extract_league_name_falls_back_to_legacy_league() -> None:
    payload = {
        "league": {"name": "Champion League I"},
    }

    assert _extract_league_name(payload) == "Champion League I"
