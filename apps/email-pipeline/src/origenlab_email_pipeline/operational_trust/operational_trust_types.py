"""Core types and allowlists for operational trust checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_FIT_BUCKETS = frozenset({"high_fit", "medium_fit", "low_fit", ""})
ALLOWED_BUYER_KINDS = frozenset(
    {
        "hospital",
        "universidad",
        "publico",
        "municipal",
        "gobierno",
        "agricola",
        "",
    }
)

AUDIT_DB_LINE_RE = re.compile(
    r"\*\*Base de datos usada:\*\*\s*`([^`]+)`",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TrustCheck:
    check_id: str
    ok: bool
    critical: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "ok": self.ok,
            "critical": self.critical,
            "message": self.message,
            "details": self.details,
        }
