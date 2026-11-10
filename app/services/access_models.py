from __future__ import annotations

from dataclasses import dataclass

from app.db.models import ClanRole


@dataclass(slots=True)
class AccessCheckResult:
    allowed: bool
    role: ClanRole | None


class AccessDeniedError(PermissionError):
    pass
