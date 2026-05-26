"""Redact operator deal previews before any public/dashboard export."""

from __future__ import annotations

import copy
import re
from typing import Any

# Chilean RUT patterns (with optional dots/dash)
_RUT_RE = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}[-–]?\d\b|\b\d{7,8}[-–]?[\dkK]\b")
# Long numeric bank / transfer IDs
_LONG_NUMERIC_ID_RE = re.compile(r"\b(?:INT_EMP)?\d{12,}\b")
# Chile bank account-ish runs (16–20 digits)
_BANK_ACCOUNT_RE = re.compile(r"\b\d{16,20}\b")
# Email is OK; street addresses heuristic (Camino + number)
_STREET_ADDRESS_RE = re.compile(
    r"\b(?:camino|av\.|avenida|calle|pasaje)\s+[\w\s]+\d+",
    re.IGNORECASE,
)
_WISE_TRANSFER_ID_RE = re.compile(r"\b2152655677\b")
_OPERATION_ID_RE = re.compile(r"\bINT_EMP\d+\b")
# Wise PDF filenames embed the transfer id after __transfer__
_WISE_FILENAME_ID_RE = re.compile(r"__transfer__\d{6,}")

_SENSITIVE_EVENT_KEYS = frozenset(
    {"operation_id", "transfer_id", "bank_account", "rut", "delivery_address"}
)


def mask_transfer_id(transfer_id: str) -> str:
    tid = (transfer_id or "").strip()
    if len(tid) <= 4:
        return "****"
    return f"****{tid[-4:]}"


def redact_filename(filename: str) -> str:
    if not filename:
        return filename
    out = _WISE_FILENAME_ID_RE.sub(lambda _m: f"__transfer__{mask_transfer_id('0000000000')}", filename)
    return redact_text(out)


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    out = _OPERATION_ID_RE.sub("[REDACTED_OPERATION_ID]", out)
    out = _WISE_TRANSFER_ID_RE.sub(lambda m: mask_transfer_id(m.group(0)), out)
    out = _WISE_FILENAME_ID_RE.sub(lambda _m: f"__transfer__{mask_transfer_id('0000000000')}", out)
    out = _LONG_NUMERIC_ID_RE.sub("[REDACTED_ID]", out)
    out = _BANK_ACCOUNT_RE.sub("[REDACTED_ACCOUNT]", out)
    out = _RUT_RE.sub("[REDACTED_RUT]", out)
    out = _STREET_ADDRESS_RE.sub("[REDACTED_ADDRESS]", out)
    return out


def _redact_event(ev: dict[str, Any]) -> dict[str, Any]:
    clean = dict(ev)
    for key in list(clean.keys()):
        if key in _SENSITIVE_EVENT_KEYS:
            if key == "transfer_id" and clean.get(key):
                clean[key] = mask_transfer_id(str(clean[key]))
            else:
                clean[key] = "[REDACTED]"
        elif isinstance(clean[key], str):
            clean[key] = redact_text(clean[key])
    if "summary" in clean and "transfer" in str(clean.get("summary", "")).lower():
        tid = ev.get("transfer_id")
        if tid:
            clean["summary"] = redact_text(str(ev.get("summary", "")))
    return clean


def _redact_field_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return meta
    clean = dict(meta)
    if "value" in clean and isinstance(clean["value"], str):
        clean["value"] = redact_text(clean["value"])
    return clean


def redact_preview_for_public(preview: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy safe for dashboard/API surfaces (no PII/payment secrets)."""
    out = copy.deepcopy(preview)
    out.pop("public_export", None)
    out.pop("corpus_validation", None)
    out["export_kind"] = "public_redacted"

    fields = out.get("fields") or {}
    if "supplier_payment_transfer_id" in fields:
        tid_meta = fields["supplier_payment_transfer_id"]
        if tid_meta and tid_meta.get("value"):
            tid_meta = dict(tid_meta)
            tid_meta["value"] = mask_transfer_id(str(tid_meta["value"]))
            tid_meta["source"] = "redacted:transfer_id_last4"
            fields["supplier_payment_transfer_id"] = tid_meta

    for key, meta in list(fields.items()):
        fields[key] = _redact_field_meta(meta)  # type: ignore[assignment]

    out["fields"] = fields

    events = out.get("events") or []
    out["events"] = [_redact_event(ev) for ev in events if isinstance(ev, dict)]

    for section in ("supplier", "client"):
        block = out.get(section)
        if isinstance(block, dict):
            for k, v in list(block.items()):
                if isinstance(v, str):
                    block[k] = redact_text(v)
                elif isinstance(v, list):
                    block[k] = [redact_text(x) if isinstance(x, str) else x for x in v]

    evidence = out.get("evidence")
    if isinstance(evidence, dict):
        for em in evidence.get("emails") or []:
            if isinstance(em, dict) and isinstance(em.get("subject"), str):
                em["subject"] = redact_text(em["subject"])
        for att in evidence.get("attachments") or []:
            if isinstance(att, dict) and isinstance(att.get("filename"), str):
                att["filename"] = redact_filename(att["filename"])

    notes = out.get("operator_notes")
    if isinstance(notes, list):
        out["operator_notes"] = [redact_text(n) if isinstance(n, str) else n for n in notes]

    out["public_export_policy"] = {
        "bank_accounts": "omitted",
        "ruts": "omitted",
        "personal_addresses": "omitted",
        "payment_operation_ids": "omitted",
        "transfer_ids": "last4_only",
    }
    return out


def public_preview_must_not_contain(text: str) -> list[str]:
    """Return list of forbidden patterns still present (empty = OK)."""
    violations: list[str] = []
    if _OPERATION_ID_RE.search(text):
        violations.append("operation_id")
    if _WISE_TRANSFER_ID_RE.search(text):
        violations.append("full_wise_transfer_id")
    if _WISE_FILENAME_ID_RE.search(text):
        violations.append("wise_filename_transfer_id")
    if _RUT_RE.search(text):
        violations.append("rut")
    if _BANK_ACCOUNT_RE.search(text):
        violations.append("bank_account")
    if "INT_EMP" in text:
        violations.append("bancochile_operation_prefix")
    return violations
