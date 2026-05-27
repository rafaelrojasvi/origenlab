"""Redaction rules for catalog Postgres mirror (Phase 8C)."""

from __future__ import annotations

import re
from typing import Any

# Legacy bug: alias-style sanitizer removed spaces before lowercase letters/digits.
_BROKEN_PROSE_JOIN_RE = re.compile(r"\s+(?=[a-z\d])")

# Targeted repairs for known Spanish join artifacts (Postgres rows synced before fix).
_PROSE_JOIN_REPAIRS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"cotizacióny\b", re.I), "cotización y"),
    (re.compile(r"porcliente\b", re.I), "por cliente"),
    (re.compile(r"cantidad(\d)", re.I), r"cantidad \1"),
    (re.compile(r"antesde\b", re.I), "antes de"),
    (re.compile(r"montoes\b", re.I), "monto es"),
    (re.compile(r"Monto(\d)", re.I), r"Monto \1"),
)

# Fields that must keep human-readable Spanish spacing (never alias-collapse).
CATALOG_MIRROR_PROSE_FIELDS: frozenset[str] = frozenset(
    {
        "display_name",
        "brand",
        "manufacturer_name",
        "public_summary",
        "model_number",
        "website_slug",
        "availability_note",
        "price_notes",
        "payment_terms",
        "delivery_terms",
        "spec_value",
        "spec_key",
        "supplier_org_name",
        "link_ref",
    }
)

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


def repair_catalog_prose_spacing(value: str) -> str:
    """Fix legacy joined-word spacing; leave already-correct prose unchanged."""
    out = value
    for pattern, replacement in _PROSE_JOIN_REPAIRS:
        out = pattern.sub(replacement, out)
    return out


def assert_catalog_prose_spacing(value: str | None, *, field: str) -> None:
    """Reject known joined-word artifacts in operator-facing Spanish prose."""
    if value is None or value == "":
        return
    for pattern, _replacement in _PROSE_JOIN_REPAIRS:
        if pattern.search(value):
            raise CatalogMirrorSafetyError(
                f"joined-word spacing in {field}: matched {pattern.pattern!r}"
            )


def prepare_catalog_mirror_text(value: str | None, *, field: str) -> str | None:
    """Repair legacy spacing, then enforce mirror safety (read/API path)."""
    if value is None or value == "":
        return value
    cleaned = repair_catalog_prose_spacing(value)
    assert_mirror_text_safe(cleaned, field=field)
    assert_catalog_prose_spacing(cleaned, field=field)
    return cleaned


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
            field = f"{table}.{key}"
            if key in CATALOG_MIRROR_PROSE_FIELDS:
                row[key] = prepare_catalog_mirror_text(value, field=field)
            else:
                assert_mirror_text_safe(value, field=field)
