import re

_TAG_ALLOWED = re.compile(r"^[A-Z0-9]+$")


class TagNormalizationError(ValueError):
    pass


def normalize_tag(raw_tag: str) -> str:
    tag = raw_tag.strip().upper().replace("O", "0")
    if not tag:
        raise TagNormalizationError("Tag is empty")
    if tag.startswith("#"):
        tag = tag[1:]
    if not _TAG_ALLOWED.match(tag):
        raise TagNormalizationError(f"Invalid tag format: {raw_tag}")
    return f"#{tag}"


def tag_for_url(tag: str) -> str:
    normalized = normalize_tag(tag)
    return normalized.replace("#", "%23")
