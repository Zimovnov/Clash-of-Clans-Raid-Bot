from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings


_MONTH_NAMES = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


@lru_cache(maxsize=1)
def get_display_timezone() -> ZoneInfo:
    timezone_name = get_settings().display_timezone
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_utc_offset(value: datetime) -> str:
    offset = value.utcoffset() or timedelta()
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"


def _format_timezone_label(value: datetime) -> str:
    return f"({_format_utc_offset(value)})"


def format_datetime_human(value: datetime | None) -> str:
    if value is None:
        return "-"

    localized = _ensure_aware_utc(value).astimezone(get_display_timezone())
    month_name = _MONTH_NAMES[localized.month]
    return (
        f"{localized.day} {month_name} {localized.year} года "
        f"{localized:%H:%M} {_format_timezone_label(localized)}"
    )
