from datetime import UTC, datetime

from app.core.dates import format_datetime_human


def test_format_datetime_human_uses_moscow_time_and_russian_month() -> None:
    value = datetime(2026, 3, 22, 12, 46, tzinfo=UTC)

    assert format_datetime_human(value) == "22 марта 2026 года 15:46 (UTC+3)"


def test_format_datetime_human_returns_dash_for_none() -> None:
    assert format_datetime_human(None) == "-"
