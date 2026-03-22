from datetime import UTC, datetime, timedelta

from app.services.classifier import ClassificationContext, is_newbie


def test_newbie_when_first_seen_since_raid_start() -> None:
    now = datetime.now(UTC)
    raid_start = now - timedelta(days=2)

    assert is_newbie(raid_start + timedelta(hours=1), ClassificationContext(now=now, raid_start_at=raid_start))


def test_newbie_when_seen_within_7_days_even_if_before_raid_start() -> None:
    now = datetime.now(UTC)
    raid_start = now - timedelta(days=2)

    assert is_newbie(now - timedelta(days=6), ClassificationContext(now=now, raid_start_at=raid_start))


def test_not_newbie_when_seen_older_than_7_days() -> None:
    now = datetime.now(UTC)
    raid_start = now - timedelta(days=2)

    assert not is_newbie(now - timedelta(days=8), ClassificationContext(now=now, raid_start_at=raid_start))


def test_not_newbie_when_seen_before_bootstrap_baseline() -> None:
    now = datetime.now(UTC)
    raid_start = now - timedelta(days=2)
    baseline_at = now - timedelta(hours=1)

    assert not is_newbie(
        now - timedelta(days=1),
        ClassificationContext(
            now=now,
            raid_start_at=raid_start,
            newbie_baseline_at=baseline_at,
        ),
    )
