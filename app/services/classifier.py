from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.models import ReportCategory


@dataclass(slots=True)
class PlayerClassificationInput:
    tag: str
    name: str
    attacks_used: int
    is_current_member: bool
    was_seen_during_raid: bool
    first_seen_in_clan_at: datetime | None


@dataclass(slots=True)
class ClassificationContext:
    now: datetime
    raid_start_at: datetime | None
    newbie_window_days: int = 7
    newbie_baseline_at: datetime | None = None


@dataclass(slots=True)
class ClassificationResult:
    category: ReportCategory
    is_newbie: bool
    is_left_clan: bool


def is_newbie(first_seen_in_clan_at: datetime | None, ctx: ClassificationContext) -> bool:
    if first_seen_in_clan_at is None:
        return False

    seen_at = first_seen_in_clan_at
    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=UTC)

    if ctx.newbie_baseline_at is not None:
        baseline_at = ctx.newbie_baseline_at
        if baseline_at.tzinfo is None:
            baseline_at = baseline_at.replace(tzinfo=UTC)
        if seen_at <= baseline_at:
            return False

    if ctx.raid_start_at and seen_at >= ctx.raid_start_at:
        return True

    return seen_at >= (ctx.now - timedelta(days=ctx.newbie_window_days))


def classify_player(player: PlayerClassificationInput, ctx: ClassificationContext) -> ClassificationResult:
    left_clan = player.was_seen_during_raid and not player.is_current_member
    newbie = is_newbie(player.first_seen_in_clan_at, ctx)

    if left_clan:
        return ClassificationResult(category=ReportCategory.LEFT_CLAN, is_newbie=newbie, is_left_clan=True)
    if newbie:
        return ClassificationResult(category=ReportCategory.NEWBIE, is_newbie=True, is_left_clan=False)
    if player.attacks_used == 0:
        return ClassificationResult(category=ReportCategory.KICK, is_newbie=False, is_left_clan=False)
    if 1 <= player.attacks_used <= 5:
        return ClassificationResult(category=ReportCategory.QUESTIONABLE, is_newbie=False, is_left_clan=False)
    return ClassificationResult(category=ReportCategory.OK, is_newbie=False, is_left_clan=False)
