"""Redaction rules for lead_intel Postgres mirror (Phase 10D)."""

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
        r"\bbeneficiario\b",
        r"\brut\b",
        r"mail\.google",
        r"source_file",
        r"transfer_id",
        r"operation_id",
        r"evidence_email_id",
        r"evidence_attachment_id",
        r"/home/",
        r"reports/in/",
        r"reports/out/",
        r"\.sqlite",
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
        "input_file_name",
        "batch_key",
        "input_priority_score",
        "role_title",
    }
)

LEAD_MIRROR_PROSE_FIELDS: frozenset[str] = frozenset(
    {
        "organization_name",
        "contact_name",
        "sector",
        "region",
        "likely_need",
        "product_angle",
        "evidence_note",
        "spanish_message_angle",
        "block_or_review_reason",
        "recommended_next_action",
        "recommended_message_angle",
        "why_this_lead",
        "suggested_subject",
        "suggested_body_preview",
        "safety_note",
        "reason_label",
    }
)


class LeadResearchMirrorSafetyError(ValueError):
    """Raised when mirror payload contains forbidden content."""


def assert_mirror_text_safe(value: str, *, field: str) -> None:
    for pattern in FORBIDDEN_MIRROR_TEXT_PATTERNS:
        if pattern.search(value):
            raise LeadResearchMirrorSafetyError(
                f"forbidden pattern in {field}: matched {pattern.pattern!r}"
            )
    if "mail.google.com" in value.lower() or "/mail/u/" in value.lower():
        raise LeadResearchMirrorSafetyError(f"forbidden gmail URL in {field}")


def assert_mirror_row_safe(row: dict[str, Any], *, table: str) -> None:
    for key in row:
        if key in FORBIDDEN_MIRROR_KEYS:
            raise LeadResearchMirrorSafetyError(f"forbidden key {key!r} in {table}")
    for key, val in row.items():
        if val is None or not isinstance(val, str):
            continue
        if key in LEAD_MIRROR_PROSE_FIELDS or key.endswith("_url") or key == "email":
            assert_mirror_text_safe(val, field=f"{table}.{key}")
