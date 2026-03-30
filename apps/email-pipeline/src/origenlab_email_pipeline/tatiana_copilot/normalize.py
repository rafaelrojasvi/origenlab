from __future__ import annotations

from pathlib import Path

from .loader import load_csv_rows
from .schemas import ExampleRecord


def _boolish(v: str | None) -> bool:
    return (v or "").strip().lower() in {"y", "yes", "true", "1"}


def _freshness_bucket(date_iso: str | None) -> str | None:
    if not date_iso or len(date_iso) < 4:
        return None
    year = date_iso[:4]
    if year < "2017":
        return "legacy"
    if year < "2020":
        return "recent_2017_2019"
    return "modern_2020_plus"


def _language_signal(row: dict[str, str]) -> str | None:
    risks = (row.get("risk_flags") or "").lower()
    if "non_spanish" in risks:
        return "likely_non_spanish"
    return "likely_spanish"


def _contamination_signal(row: dict[str, str]) -> str | None:
    risks = (row.get("risk_flags") or "").lower()
    if "hybrid_forward_or_quote_heavy" in risks:
        return "forward_quote_heavy"
    if "hybrid_forward_or_quote_moderate" in risks:
        return "forward_quote_moderate"
    if (row.get("heavy_reply_tail") or "").strip().lower() == "y":
        return "heavy_reply_tail"
    return "low_contamination"


def normalize_row(row: dict[str, str], source_file: Path, kind: str) -> ExampleRecord:
    rank = (row.get("review_priority_rank") or "").strip()
    source_row_id = (row.get("id") or "").strip()
    exid = f"{source_file.stem}:{rank or source_row_id or 'na'}"
    subject = (row.get("subject") or "").strip()
    body = (row.get("body_for_review") or "").strip()
    label = (row.get("human_label") or row.get("auto_label") or "").strip()
    date_iso = (row.get("date_iso") or "").strip() or None
    search_text = f"Subject: {subject}\n{body}".strip()

    keep_style = _boolish(row.get("keep_for_style_guide"))
    keep_retr = _boolish(row.get("keep_for_retrieval_later"))

    meta = {
        "review_priority_rank": row.get("review_priority_rank", ""),
        "marketing_rank_score": row.get("marketing_rank_score", ""),
        "marketing_rank_notes": row.get("marketing_rank_notes", ""),
        "risk_flags": row.get("risk_flags", ""),
        "likely_outbound_external": row.get("likely_outbound_external", ""),
        "intent_primary_category": row.get("intent_primary_category", ""),
        "intent_commercial_subtype": row.get("intent_commercial_subtype", ""),
    }
    return ExampleRecord(
        example_id=exid,
        source_file=str(source_file),
        source_row_id=source_row_id,
        kind=kind,
        label=label,
        subject=subject,
        body_text=body,
        search_text=search_text,
        date_iso=date_iso,
        freshness_bucket=_freshness_bucket(date_iso),
        language_signal=_language_signal(row),
        contamination_signal=_contamination_signal(row),
        keep_for_style_guide=keep_style,
        keep_for_retrieval_later=keep_retr,
        metadata=meta,
    )


def build_example_sets(
    *,
    labeled_final_csv: Path,
    style_seed_csv: Path,
    retrieval_seed_csv: Path,
) -> tuple[list[ExampleRecord], list[ExampleRecord]]:
    """
    Return (style_examples, retrieval_examples) from curated artifacts.
    """
    style_rows = load_csv_rows(style_seed_csv)
    retr_rows = load_csv_rows(retrieval_seed_csv)
    # labeled_final_csv is loaded to preserve traceability and provide stable ids/labels if needed.
    # We keep seeds as source of truth for v1 retrieval pools.
    _ = load_csv_rows(labeled_final_csv)

    style_examples = [normalize_row(r, style_seed_csv, "style") for r in style_rows]
    retrieval_examples = [normalize_row(r, retrieval_seed_csv, "retrieval") for r in retr_rows]
    return style_examples, retrieval_examples
