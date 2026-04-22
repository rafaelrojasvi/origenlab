"""Pure / side-effect–free helpers for the volume marketing (broad) lane.

``process_broad_marketing_contacts`` CLI (scripts) composes I/O, readonly SQLite, and
gate context; this module implements row processing and output shaping only.

For operator entrypoint and I/O, see :mod:`scripts.leads.process_broad_marketing_contacts`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidate_export_gate import GateContext, evaluate_export_eligibility
from .csv_contracts import (
    extract_email_from_aliases,
    normalize_confidence,
    sanitize_csv_text,
    source_is_official_registry_exception,
    source_looks_third_party,
    validate_confidence,
    validate_email_syntax,
    validate_source_url,
)

REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "institution_name",
    "region",
    "city",
    "type",
    "contact_email",
    "contact_label",
    "source_url",
    "confidence",
)

SEND_READY_FIELDS: tuple[str, ...] = (
    "case_id",
    "contact_email",
    "email_source",
    "institution_name",
    "region",
    "city",
    "type",
    "contact_label",
    "source_url",
    "confidence",
    "fit_signal",
    "variant_type",
)

_GENERIC_LABELS: frozenset[str] = frozenset(
    {
        "",
        "contact",
        "contacto",
        "email",
        "general",
        "n/a",
        "na",
        "s/a",
        "info",
        "informacion",
        "información",
        "solicitud",
        "admin",
    }
)


@dataclass(frozen=True, slots=True)
class BroadMarketingProcessResult:
    """Result of classifying and splitting reviewed marketing contact rows (no I/O)."""

    safe_rows: list[dict[str, str]]
    blocked_rows: list[dict[str, str]]
    review_rows: list[dict[str, str]]
    send_ready_rows: list[dict[str, str]]


def load_master_norms_from_csv(path: Path) -> set[str]:
    """Load normalized email keys from do-not-repeat master (email_norm or email)."""
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            em = str(row.get("email_norm") or row.get("email") or "").strip().lower()
            if em:
                out.add(em)
    return out


def row_schema_errors(row: dict[str, str]) -> list[str]:
    err: list[str] = []
    em = validate_email_syntax(extract_email_from_aliases(row, ("contact_email",)))
    if not em:
        err.append("invalid_email")
    conf = normalize_confidence(row.get("confidence", ""))
    if not validate_confidence(conf) or conf not in {"high", "medium", "low"}:
        err.append("invalid_confidence")
    src = str(row.get("source_url") or "").strip()
    if not src:
        err.append("missing_source_url")
    elif not validate_source_url(src):
        err.append("invalid_source_url")
    fs = str(row.get("fit_signal") or "").strip()
    if fs and len(fs) > 2000:
        err.append("fit_signal_too_long")
    return err


def is_generic_label(label: str) -> bool:
    return str(label or "").strip().lower() in _GENERIC_LABELS


def is_weak_fit(fit_signal: str) -> bool:
    return len(str(fit_signal or "").strip()) < 4


def augment_row(base: dict[str, str], **extra: str) -> dict[str, str]:
    o = dict(base)
    for k, v in extra.items():
        o[k] = v
    return o


def process_reviewed_marketing_rows(
    rows: list[dict[str, str]],
    *,
    master_email_norms: set[str],
    ctx: GateContext,
    variant_type: str = "broad_marketing",
) -> BroadMarketingProcessResult:
    """
    Classify each input row into safe / blocked / review buckets and build send_ready rows
    (same policy as the legacy in-script loop).
    """
    safe_rows: list[dict[str, str]] = []
    blocked_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    send_ready: list[dict[str, str]] = []

    seen_batch: dict[str, int] = {}
    case_seq = 0

    for i, raw in enumerate(rows, start=2):
        base = {k: sanitize_csv_text(raw.get(k, "")) for k in raw.keys()}
        line_errors = row_schema_errors(raw)
        em = validate_email_syntax(extract_email_from_aliases(raw, ("contact_email",)))
        inst = str(raw.get("institution_name") or "").strip()

        if line_errors:
            blocked_rows.append(augment_row(base, block_reason=";".join(line_errors), source_line=str(i)))
            continue

        assert em is not None
        if em in seen_batch:
            blocked_rows.append(
                augment_row(
                    base,
                    block_reason="duplicate_input",
                    source_line=str(i),
                    duplicate_of_line=str(seen_batch[em]),
                )
            )
            continue
        seen_batch[em] = i

        if em in master_email_norms:
            blocked_rows.append(augment_row(base, block_reason="do_not_repeat_master", source_line=str(i)))
            continue

        gate = evaluate_export_eligibility(contact_email=em, institution_name=inst, ctx=ctx)
        if not gate.eligible:
            blocked_rows.append(augment_row(base, block_reason=";".join(gate.reasons), source_line=str(i)))
            continue

        src = str(raw.get("source_url") or "").strip()
        conf = normalize_confidence(raw.get("confidence", ""))
        review_reasons: list[str] = []
        if conf == "low":
            review_reasons.append("low_confidence")
        if source_looks_third_party(src) and not source_is_official_registry_exception(src):
            review_reasons.append("third_party_source")
        if is_generic_label(str(raw.get("contact_label") or "")) and is_weak_fit(
            str(raw.get("fit_signal") or "")
        ):
            review_reasons.append("generic_label_weak_fit")

        extra: dict[str, str] = {"source_line": str(i)}
        if review_reasons:
            review_rows.append(augment_row(base, review_reason=";".join(review_reasons), **extra))
        else:
            case_seq += 1
            case_id = f"MKT-{case_seq:05d}"
            safe_row = augment_row(base, case_id=case_id, **extra)
            safe_rows.append(safe_row)
            send_ready.append(
                {
                    "case_id": case_id,
                    "contact_email": validate_email_syntax(
                        extract_email_from_aliases(safe_row, ("contact_email",))
                    )
                    or "",
                    "email_source": "marketing_contacts",
                    "institution_name": safe_row.get("institution_name", ""),
                    "region": safe_row.get("region", ""),
                    "city": safe_row.get("city", ""),
                    "type": safe_row.get("type", ""),
                    "contact_label": safe_row.get("contact_label", ""),
                    "source_url": safe_row.get("source_url", ""),
                    "confidence": safe_row.get("confidence", ""),
                    "fit_signal": safe_row.get("fit_signal", ""),
                    "variant_type": variant_type,
                }
            )

    return BroadMarketingProcessResult(
        safe_rows=safe_rows,
        blocked_rows=blocked_rows,
        review_rows=review_rows,
        send_ready_rows=send_ready,
    )


def safe_output_fieldnames() -> list[str]:
    return list(
        dict.fromkeys(list(REQUIRED_INPUT_COLUMNS) + ["fit_signal", "case_id", "source_line"])
    )


def blocked_output_fieldnames() -> list[str]:
    return list(
        dict.fromkeys(
            list(REQUIRED_INPUT_COLUMNS)
            + ["fit_signal", "block_reason", "source_line", "duplicate_of_line"]
        )
    )


def review_output_fieldnames() -> list[str]:
    return list(
        dict.fromkeys(list(REQUIRED_INPUT_COLUMNS) + ["fit_signal", "review_reason", "source_line"])
    )


def build_marketing_contacts_summary(
    *,
    db_path: Path,
    workspace: Path,
    input_path: Path,
    master_path: Path,
    gmail_user: str,
    sent_folders: list[str] | tuple[str, ...],
    input_row_count: int,
    result: BroadMarketingProcessResult,
    out_safe: Path,
    out_blocked: Path,
    out_review: Path,
    out_send: Path,
    out_summary: Path,
) -> dict[str, Any]:
    """Build the marketing_contacts_summary.json object (keys stable; sort_keys in caller)."""
    return {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path.resolve()),
        "workspace": str(workspace.resolve()),
        "input": str(input_path.resolve()),
        "master_path": str(master_path.resolve()),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "counts": {
            "input_rows": input_row_count,
            "safe_to_send": len(result.safe_rows),
            "blocked": len(result.blocked_rows),
            "needs_manual_review": len(result.review_rows),
            "send_ready_marketing": len(result.send_ready_rows),
        },
        "outputs": {
            "marketing_safe_to_send": str(out_safe.resolve()),
            "marketing_blocked_already_known": str(out_blocked.resolve()),
            "marketing_needs_manual_review": str(out_review.resolve()),
            "send_ready_marketing": str(out_send.resolve()),
            "marketing_contacts_summary": str(out_summary.resolve()),
        },
    }
