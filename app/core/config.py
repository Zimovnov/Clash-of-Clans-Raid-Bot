from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str | None = Field(default=None, alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    clash_api_token: str = Field(alias="CLASH_API_TOKEN")
    app_timezone: str = Field(default="UTC", alias="APP_TIMEZONE")
    display_timezone: str = Field(default="Europe/Moscow", alias="DISPLAY_TIMEZONE")
    superadmin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="SUPERADMIN_TELEGRAM_IDS")
    sync_interval_hours: int = Field(default=3, alias="SYNC_INTERVAL_HOURS")
    report_time_utc: str = Field(default="08:02", alias="REPORT_TIME_UTC")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    clash_api_base_url: str = Field(default="https://api.clashofclans.com/v1", alias="CLASH_API_BASE_URL")
    internal_api_token: str | None = Field(default=None, alias="INTERNAL_API_TOKEN")
    api_docs_enabled: bool = Field(default=False, alias="API_DOCS_ENABLED")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    report_retry_delays_minutes: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [5, 15, 30, 120],
        alias="REPORT_RETRY_DELAYS_MINUTES",
    )

    @field_validator("bot_token", "internal_api_token", mode="before")
    @classmethod
    def parse_optional_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("superadmin_telegram_ids", mode="before")
    @classmethod
    def parse_superadmins(cls, value: str | int | list[int] | None) -> list[int]:
        if value is None:
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        value = value.strip()
        if not value:
            return []
        return [int(v.strip()) for v in value.split(",") if v.strip()]

    @field_validator("report_retry_delays_minutes", mode="before")
    @classmethod
    def parse_retry_delays(cls, value: str | int | list[int] | None) -> list[int]:
        if value is None:
            return [5, 15, 30, 120]
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        value = value.strip()
        if not value:
            return [5, 15, 30, 120]
        return [int(v.strip()) for v in value.split(",") if v.strip()]

    @property
    def report_hour(self) -> int:
        hour, _ = self.report_time_utc.split(":", maxsplit=1)
        return int(hour)

    @property
    def report_minute(self) -> int:
        _, minute = self.report_time_utc.split(":", maxsplit=1)
        return int(minute)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
