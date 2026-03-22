from datetime import UTC, datetime, timedelta

from app.db.models import ReportCategory
from app.services.classifier import ClassificationContext, PlayerClassificationInput, classify_player


def test_classifies_kick_for_zero_attacks_non_newbie() -> None:
    now = datetime.now(UTC)
    ctx = ClassificationContext(now=now, raid_start_at=now - timedelta(days=2))
    player = PlayerClassificationInput(
        tag="#AAA",
        name="Player",
        attacks_used=0,
        is_current_member=True,
        was_seen_during_raid=True,
        first_seen_in_clan_at=now - timedelta(days=20),
    )

    result = classify_player(player, ctx)
    assert result.category == ReportCategory.KICK


def test_classifies_questionable_for_1_to_5_attacks() -> None:
    now = datetime.now(UTC)
    ctx = ClassificationContext(now=now, raid_start_at=now - timedelta(days=2))
    player = PlayerClassificationInput(
        tag="#AAA",
        name="Player",
        attacks_used=3,
        is_current_member=True,
        was_seen_during_raid=True,
        first_seen_in_clan_at=now - timedelta(days=20),
    )

    result = classify_player(player, ctx)
    assert result.category == ReportCategory.QUESTIONABLE


def test_classifies_ok_for_more_than_5_attacks() -> None:
    now = datetime.now(UTC)
    ctx = ClassificationContext(now=now, raid_start_at=now - timedelta(days=2))
    player = PlayerClassificationInput(
        tag="#AAA",
        name="Player",
        attacks_used=6,
        is_current_member=True,
        was_seen_during_raid=True,
        first_seen_in_clan_at=now - timedelta(days=20),
    )

    result = classify_player(player, ctx)
    assert result.category == ReportCategory.OK
