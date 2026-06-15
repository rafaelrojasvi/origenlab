"""Publish ChileCompra API equipment queue CSV for dashboard/API consumption."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.chilecompra_api import (
    VALIDITY_STATUS_CLOSES_TODAY,
    VALIDITY_STATUS_MISSING_CLOSE_DATE,
    VALIDITY_STATUS_OPEN,
)
from origenlab_email_pipeline.equipment_first_licitacion_queue import parse_close_date
from origenlab_email_pipeline.equipment_first_operator_queue import OPERATOR_FIELDS

CHILECOMPRA_REVIEW_NOTE = (
    "ChileCompra API candidate; revisar bases, fechas, proveedor y margen antes de actuar."
)
CHILECOMPRA_SAFE_CHANNEL = "mercado_publico_only"
CHILECOMPRA_CONTACT_STATUS = "review_required"
CHILECOMPRA_CONTACT_STATUS_MISSING_CLOSE_DATE = "review_required_missing_close_date"

DASHBOARD_ACTIVE_VALIDITY_STATUSES = frozenset(
    {
        VALIDITY_STATUS_OPEN,
        VALIDITY_STATUS_CLOSES_TODAY,
        VALIDITY_STATUS_MISSING_CLOSE_DATE,
    }
)

NEXT_ACTION_SORT_ORDER: dict[str, int] = {
    "quote_now": 0,
    "needs_supplier_quote": 1,
    "contact_after_close": 2,
    "account_intelligence_only": 3,
    "skip_consumables": 4,
}

PUBLISHED_DASHBOARD_FIELDS: tuple[str, ...] = (
    *OPERATOR_FIELDS,
    "title",
    "fit_score",
    "reason",
    "contact_email",
    "chilecompra_status_code",
    "chilecompra_status",
    "validity_status",
    "api_checked_at_utc",
    "source",
)

_CHILECOMPRA_API_QUEUE_PREFIX = "equipment_first_operator_queue_chilecompra_api_"


def default_canonical_operator_queue_path(
    reports_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return (
        reports_dir
        / "active"
        / "current"
        / f"equipment_first_operator_queue_{stamp}.csv"
    )


def load_chilecompra_source_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"ChileCompra source CSV missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_fit_score(value: str | None) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return 0


def _supplier_needed_value(next_action: str) -> str:
    return "yes" if next_action in ("quote_now", "needs_supplier_quote") else "no"


def _contact_status_for_validity(validity_status: str) -> str:
    if validity_status == VALIDITY_STATUS_MISSING_CLOSE_DATE:
        return CHILECOMPRA_CONTACT_STATUS_MISSING_CLOSE_DATE
    return CHILECOMPRA_CONTACT_STATUS


def is_dashboard_active_chilecompra_row(row: dict[str, str]) -> bool:
    validity_status = (row.get("validity_status") or "").strip()
    return validity_status in DASHBOARD_ACTIVE_VALIDITY_STATUSES


def enrich_chilecompra_row_for_dashboard(row: dict[str, str]) -> dict[str, str]:
    """Add dashboard/operator enrichment columns without inventing buyer emails."""
    next_action = (row.get("next_action") or "").strip()
    supplier_needed = _supplier_needed_value(next_action)
    validity_status = (row.get("validity_status") or "").strip()
    contact_status = _contact_status_for_validity(validity_status)
    note_parts = [
        CHILECOMPRA_REVIEW_NOTE,
        (row.get("reason") or "").strip(),
        f"fit_score={row.get('fit_score', '').strip()}",
    ]
    if validity_status == VALIDITY_STATUS_MISSING_CLOSE_DATE:
        note_parts.append("missing_close_date; revisar fecha de cierre en Mercado Público")
    enriched = {
        "priority_rank": (row.get("priority_rank") or "").strip(),
        "codigo_licitacion": (row.get("codigo_licitacion") or "").strip(),
        "buyer": (row.get("buyer") or "").strip(),
        "region": (row.get("region") or "").strip(),
        "close_date": (row.get("close_date") or "").strip(),
        "equipment_category": (row.get("equipment_category") or "").strip(),
        "item_description": (row.get("item_description") or "")[:500],
        "next_action": next_action,
        "contact_status": contact_status,
        "safe_channel": CHILECOMPRA_SAFE_CHANNEL,
        "supplier_needed": supplier_needed,
        "supplier_contact": supplier_needed if supplier_needed == "yes" else "",
        "gmail_prior_thread": (row.get("gmail_prior_thread") or "none").strip() or "none",
        "outreach_state": (row.get("outreach_state") or "review_required").strip() or "review_required",
        "operator_note": " | ".join(part for part in note_parts if part)[:400],
        "title": (row.get("title") or "").strip(),
        "fit_score": str(row.get("fit_score") or "").strip(),
        "reason": (row.get("reason") or "").strip(),
        "contact_email": "",
        "chilecompra_status_code": (row.get("chilecompra_status_code") or "").strip(),
        "chilecompra_status": (row.get("chilecompra_status") or "").strip(),
        "validity_status": validity_status,
        "api_checked_at_utc": (row.get("api_checked_at_utc") or "").strip(),
        "source": (row.get("source") or "chilecompra_api").strip() or "chilecompra_api",
    }
    return enriched


def sort_chilecompra_dashboard_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort by fit_score desc, next_action priority, close_date asc."""

    def _sort_key(row: dict[str, str]) -> tuple[int, int, float, str]:
        next_action = (row.get("next_action") or "").strip()
        close_dt = parse_close_date(row.get("close_date") or "")
        close_sort = close_dt.timestamp() if close_dt is not None else float("inf")
        return (
            -_parse_fit_score(row.get("fit_score")),
            NEXT_ACTION_SORT_ORDER.get(next_action, 99),
            close_sort,
            (row.get("codigo_licitacion") or "").strip(),
        )

    sorted_rows = sorted(rows, key=_sort_key)
    ranked: list[dict[str, str]] = []
    for index, row in enumerate(sorted_rows, start=1):
        updated = dict(row)
        updated["priority_rank"] = str(index)
        ranked.append(updated)
    return ranked


def publish_chilecompra_equipment_rows(
    source_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    active_rows = [row for row in source_rows if is_dashboard_active_chilecompra_row(row)]
    enriched = [enrich_chilecompra_row_for_dashboard(row) for row in active_rows]
    return sort_chilecompra_dashboard_rows(enriched)


def write_published_dashboard_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PUBLISHED_DASHBOARD_FIELDS))
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in PUBLISHED_DASHBOARD_FIELDS} for row in rows
        )


def update_active_manifest_canonical_queue(
    active_current: Path,
    *,
    queue_filename: str,
    source_manifest: Path | None = None,
) -> dict[str, Any]:
    """Prepend published queue to manifest canonical_files when manifest already exists."""
    manifest_path = active_current / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    existing = [str(item).strip() for item in (manifest.get("canonical_files") or []) if str(item).strip()]
    filtered = [
        name
        for name in existing
        if name != queue_filename and not name.startswith(_CHILECOMPRA_API_QUEUE_PREFIX)
    ]
    manifest["canonical_files"] = [queue_filename, *filtered]
    manifest["campaign_mode"] = manifest.get("campaign_mode") or "equipment_first"

    publish_meta: dict[str, Any] = {
        "published_queue": queue_filename,
        "published_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if source_manifest is not None and source_manifest.is_file():
        try:
            source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            source_payload = {}
        publish_meta["source_manifest"] = source_manifest.name
        publish_meta["source_output_rows"] = source_payload.get("output_rows")
        publish_meta["source_detail_error_count"] = source_payload.get("detail_error_count")
    manifest["chilecompra_api_publish"] = publish_meta

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "manifest_path": str(manifest_path),
        "canonical_files": manifest["canonical_files"],
        "campaign_mode": manifest["campaign_mode"],
        "chilecompra_api_publish": publish_meta,
    }


def publish_chilecompra_equipment_queue_for_dashboard(
    *,
    source_csv: Path,
    out_csv: Path,
    source_manifest: Path | None = None,
    update_manifest: bool = False,
    active_current: Path | None = None,
) -> dict[str, Any]:
    source_rows = load_chilecompra_source_rows(source_csv)
    active_input_rows = [row for row in source_rows if is_dashboard_active_chilecompra_row(row)]
    published_rows = publish_chilecompra_equipment_rows(source_rows)
    write_published_dashboard_csv(published_rows, out_csv)

    result: dict[str, Any] = {
        "source_csv": str(source_csv),
        "out_csv": str(out_csv),
        "input_rows": len(source_rows),
        "active_input_rows": len(active_input_rows),
        "output_rows": len(published_rows),
        "excluded_rows": len(source_rows) - len(active_input_rows),
        "manifest_updated": False,
    }
    if update_manifest:
        target_active = active_current or out_csv.parent
        manifest_result = update_active_manifest_canonical_queue(
            target_active,
            queue_filename=out_csv.name,
            source_manifest=source_manifest,
        )
        result["manifest_updated"] = True
        result.update(manifest_result)
    return result
