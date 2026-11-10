from datetime import UTC, datetime, timedelta

from app.db.models import ReportCategory
from app.services.classifier import ClassificationContext, PlayerClassificationInput, classify_player


def test_left_clan_priority_over_kick() -> None:
    now = datetime.now(UTC)
    ctx = ClassificationContext(now=now, raid_start_at=now - timedelta(days=2))
    player = PlayerClassificationInput(
        tag="#LEFT",
        name="Left",
        attacks_used=0,
        is_current_member=False,
        was_seen_during_raid=True,
        first_seen_in_clan_at=now - timedelta(days=30),
    )

    result = classify_player(player, ctx)
    assert result.category == ReportCategory.LEFT_CLAN
