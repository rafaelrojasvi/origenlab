"""Redaction rules for catalog Postgres mirror (Phase 8C)."""

from __future__ import annotations

import re
from typing import Any

FORBIDDEN_MIRROR_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bbank\b",
        r"\bbanco\b",
        r"\bswift\b",
        r"\biban\b",
        r"\bcuenta\b",
        r"\bbeneficiario\b",
        r"\brut\b",
        r"gmail\.com",
        r"mail\.google",
        r"source_file",
        r"transfer_id",
        r"operation_id",
    )
)

FORBIDDEN_MIRROR_KEYS: frozenset[str] = frozenset(
    {
        "evidence_email_id",
        "evidence_attachment_id",
        "notes",
        "transfer_id",
        "operation_id",
        "source_file",
        "source_preview_path",
        "gmail_url",
        "body",
        "full_text",
        "email_body",
    }
)


class CatalogMirrorSafetyError(ValueError):
    """Raised when mirror payload contains forbidden content."""


def assert_mirror_text_safe(value: str | None, *, field: str) -> None:
    if value is None or value == "":
        return
    for pat in FORBIDDEN_MIRROR_TEXT_PATTERNS:
        if pat.search(value):
            raise CatalogMirrorSafetyError(
                f"forbidden content in {field}: matched {pat.pattern!r}"
            )


def assert_mirror_row_safe(row: dict[str, Any], *, table: str) -> None:
    for key in row:
        if key in FORBIDDEN_MIRROR_KEYS:
            raise CatalogMirrorSafetyError(f"{table}: forbidden key {key!r}")
    for key, value in row.items():
        if isinstance(value, str):
            assert_mirror_text_safe(value, field=f"{table}.{key}")
