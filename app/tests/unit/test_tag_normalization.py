import pytest

from app.core.tags import TagNormalizationError, normalize_tag


def test_normalize_tag_adds_hash_and_uppercase() -> None:
    assert normalize_tag("abc123") == "#ABC123"


def test_normalize_tag_replaces_o_with_zero() -> None:
    assert normalize_tag("#ABO12") == "#AB012"


def test_normalize_tag_rejects_invalid_chars() -> None:
    with pytest.raises(TagNormalizationError):
        normalize_tag("#AB-12")
