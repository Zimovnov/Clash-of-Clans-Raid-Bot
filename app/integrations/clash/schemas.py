from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def parse_clash_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S.000Z").replace(tzinfo=UTC)
    except ValueError:
        return None


@dataclass(slots=True)
class ClanMember:
    tag: str
    name: str


@dataclass(slots=True)
class RaidMemberStats:
    tag: str
    name: str
    attacks: int


@dataclass(slots=True)
class RaidSeason:
    start_time: datetime | None
    end_time: datetime | None
    members: list[RaidMemberStats]
    raw: dict


@dataclass(slots=True)
class PlayerProfileData:
    tag: str
    name: str
    exp_level: int | None
    town_hall_level: int | None
    builder_hall_level: int | None
    league_name: str | None
    clan_role: str | None
    raw: dict
