from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .loader import load_csv_rows
from .pilot_schemas import PilotInputCase

# Canonical CSV columns (extras preserved in PilotInputCase.extra).
CSV_CANONICAL = (
    "case_id",
    "subject",
    "body_text",
    "from_email",
    "from_name",
    "thread_hint",
    "received_at",
    "case_type",
    "notes",
)
# Aliases: first match wins when normalizing header row.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "case_id": ("case_id", "id", "pilot_case_id", "eval_case_id"),
    "subject": ("subject", "subject_raw", "mime_subject"),
    "body_text": ("body_text", "body", "body_for_review", "message_body"),
    "from_email": ("from_email", "sender_email", "email"),
    "from_name": ("from_name", "sender_name", "name"),
    "thread_hint": ("thread_hint", "thread_id", "conversation_id"),
    "received_at": ("received_at", "date_iso", "sent_at", "timestamp"),
    "case_type": ("case_type", "expected_mode", "expected_label", "label"),
    "notes": ("notes", "pilot_notes", "reviewer_hint"),
    "requester_name": ("requester_name", "client_name", "buyer_name"),
    "requester_email": ("requester_email", "client_email"),
    "requested_product_or_category": (
        "requested_product_or_category",
        "product_category",
        "product_line",
    ),
    "explicit_known_facts": ("explicit_known_facts", "confirmed_facts"),
    "missing_information": ("missing_information", "gaps", "pending_facts"),
    "notes_for_reviewer": ("notes_for_reviewer", "internal_notes"),
}


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", "_", (h or "").strip().lower())


def _build_alias_lookup(header_row: list[str]) -> dict[str, str]:
    """Map normalized header -> canonical key if recognized."""
    inv: dict[str, str] = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for a in aliases:
            inv[_norm_header(a)] = canonical
    out: dict[str, str] = {}
    for raw in header_row:
        n = _norm_header(raw)
        if n in inv:
            out[raw] = inv[n]
    return out


def _empty_to_none(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def row_to_pilot_case(row: dict[str, str], *, alias_map: dict[str, str]) -> PilotInputCase:
    def get_canonical(canonical: str) -> str:
        for k, v in row.items():
            if alias_map.get(k) == canonical:
                return v or ""
        return ""

    case_id = _empty_to_none(get_canonical("case_id"))
    if not case_id:
        raise ValueError("Every pilot row must have a non-empty case_id (or id).")

    subject = get_canonical("subject") or ""
    body = get_canonical("body_text") or ""
    if not body.strip():
        raise ValueError(f"pilot case {case_id!r} must have non-empty body_text (or body / body_for_review).")

    extras: dict[str, Any] = {}
    mapped_raw = set(alias_map.keys())
    for k, v in row.items():
        if k in mapped_raw:
            continue
        if (v or "").strip():
            extras[k] = v.strip()

    return PilotInputCase(
        case_id=case_id,
        subject=subject,
        body_text=body,
        from_email=_empty_to_none(get_canonical("from_email")),
        from_name=_empty_to_none(get_canonical("from_name")),
        thread_hint=_empty_to_none(get_canonical("thread_hint")),
        received_at=_empty_to_none(get_canonical("received_at")),
        case_type=_empty_to_none(get_canonical("case_type")),
        notes=_empty_to_none(get_canonical("notes")),
        requester_name=_empty_to_none(get_canonical("requester_name")),
        requester_email=_empty_to_none(get_canonical("requester_email")),
        requested_product_or_category=_empty_to_none(get_canonical("requested_product_or_category")),
        explicit_known_facts=_empty_to_none(get_canonical("explicit_known_facts")),
        missing_information=_empty_to_none(get_canonical("missing_information")),
        notes_for_reviewer=_empty_to_none(get_canonical("notes_for_reviewer")),
        extra=extras,
    )


def load_pilot_cases_csv(path: Path) -> list[PilotInputCase]:
    rows = load_csv_rows(path)
    if not rows:
        return []
    alias_map = _build_alias_lookup(list(rows[0].keys()))
    return [row_to_pilot_case(r, alias_map=alias_map) for r in rows]


def load_pilot_cases_jsonl(path: Path) -> list[PilotInputCase]:
    cases: list[PilotInputCase] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"JSONL line {i}: expected object, got {type(obj)}")
            row = {str(k): "" if v is None else str(v) for k, v in obj.items()}
            alias_map = _build_alias_lookup(list(row.keys()))
            cases.append(row_to_pilot_case(row, alias_map=alias_map))
    return cases


def load_pilot_cases_json_batch(path: Path) -> list[PilotInputCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "cases" in raw:
        items = raw["cases"]
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("JSON batch must be a list of cases or {\"cases\": [...]}")

    if not isinstance(items, list):
        raise ValueError("cases must be a list")
    cases: list[PilotInputCase] = []
    for i, obj in enumerate(items, start=1):
        if not isinstance(obj, dict):
            raise ValueError(f"cases[{i}] must be an object")
        row = {str(k): "" if v is None else str(v) for k, v in obj.items()}
        alias_map = _build_alias_lookup(list(row.keys()))
        cases.append(row_to_pilot_case(row, alias_map=alias_map))
    return cases


def load_pilot_input(path: Path) -> list[PilotInputCase]:
    """
    Load pilot cases from CSV, JSONL (.jsonl), or JSON array / envelope.
    """
    suf = path.suffix.lower()
    if suf == ".csv":
        return load_pilot_cases_csv(path)
    if suf == ".jsonl":
        return load_pilot_cases_jsonl(path)
    if suf == ".json":
        return load_pilot_cases_json_batch(path)
    raise ValueError(f"Unsupported pilot input type: {path} (use .csv, .jsonl, or .json)")
