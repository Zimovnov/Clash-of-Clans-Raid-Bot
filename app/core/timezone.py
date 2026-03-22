from zoneinfo import ZoneInfo

from app.core.config import get_settings


def utc_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)
