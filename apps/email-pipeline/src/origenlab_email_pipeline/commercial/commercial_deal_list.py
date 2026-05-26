"""Read-only listing of commercial deals from SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_inspector import connect_readonly

_FORBIDDEN_JSON_KEYS: frozenset[str] = frozenset(
    {
        "source_preview_path",
        "notes_json",
        "transfer_id",
        "operation_id",
        "legacy_purchase_event_id",
    }
)

_FORBIDDEN_KEY_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "body",
        "full_body",
        "body_clean",
        "body_text",
        "attachment_extract",
        "full_text",
    }
)

_LIST_SELECT = """
SELECT
  deal_key,
  client_org_name,
  supplier_org_name,
  deal_status,
  margin_status,
  client_sale_net_clp,
  client_sale_gross_clp,
  client_payment_received_clp,
  supplier_amount_paid_decimal,
  supplier_amount_paid_minor,
  freight_status,
  reconciliation_status,
  updated_at
FROM commercial_deal
"""


@dataclass(frozen=True)
class DealListFilters:
    status: str | None = None
    margin_status: str | None = None
    client: str | None = None
    supplier: str | None = None
    needs_margin_review: bool = False
    limit: int | None = None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row)))


def _sanitize_deal_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in _FORBIDDEN_JSON_KEYS:
            continue
        if any(sub in key.lower() for sub in _FORBIDDEN_KEY_SUBSTRINGS):
            continue
        out[key] = value
    return out


def _build_where(filters: DealListFilters) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.needs_margin_review:
        clauses.append("margin_status = ?")
        params.append("needs_review")
    if filters.status:
        clauses.append("deal_status = ?")
        params.append(filters.status.strip())
    if filters.margin_status and not filters.needs_margin_review:
        clauses.append("margin_status = ?")
        params.append(filters.margin_status.strip())
    if filters.client:
        needle = f"%{filters.client.strip()}%"
        clauses.append(
            "(client_org_name LIKE ? COLLATE NOCASE OR client_domain LIKE ? COLLATE NOCASE)"
        )
        params.extend([needle, needle])
    if filters.supplier:
        needle = f"%{filters.supplier.strip()}%"
        clauses.append(
            "(supplier_org_name LIKE ? COLLATE NOCASE OR supplier_domain LIKE ? COLLATE NOCASE)"
        )
        params.extend([needle, needle])
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_deal_list(
    conn: sqlite3.Connection,
    filters: DealListFilters | None = None,
) -> list[dict[str, Any]]:
    """Return safe deal summary rows matching filters."""
    f = filters or DealListFilters()
    where_sql, params = _build_where(f)
    limit_sql = ""
    if f.limit is not None and f.limit > 0:
        limit_sql = " LIMIT ?"
        params.append(int(f.limit))
    sql = f"{_LIST_SELECT}{where_sql} ORDER BY updated_at DESC, deal_key{limit_sql}"
    rows = conn.execute(sql, params).fetchall()
    return [_sanitize_deal_row(_row_to_dict(r)) for r in rows]


def list_deals(db_path: Path, filters: DealListFilters | None = None) -> list[dict[str, Any]]:
    conn = connect_readonly(db_path)
    try:
        return fetch_deal_list(conn, filters)
    finally:
        conn.close()


def _fmt_clp(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


def _fmt_supplier_paid(dec: str | None, minor: int | None) -> str:
    if not dec:
        return "—"
    if minor is not None:
        return f"EUR {dec}"
    return f"EUR {dec}"


def format_deal_list_human(deals: list[dict[str, Any]]) -> str:
    if not deals:
        return "No commercial deals found."
    lines: list[str] = []
    header = (
        f"{'deal_key':<36}  {'client':<22}  {'supplier':<22}  "
        f"{'status':<18}  {'margin':<14}  {'net CLP':>10}  {'gross CLP':>10}  "
        f"{'paid EUR':<10}  {'freight':<28}  {'updated_at'}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for d in deals:
        gross = d.get("client_payment_received_clp") or d.get("client_sale_gross_clp")
        lines.append(
            f"{str(d.get('deal_key') or ''):<36}  "
            f"{_truncate(str(d.get('client_org_name') or '—'), 22):<22}  "
            f"{_truncate(str(d.get('supplier_org_name') or '—'), 22):<22}  "
            f"{str(d.get('deal_status') or '—'):<18}  "
            f"{str(d.get('margin_status') or '—'):<14}  "
            f"{_fmt_clp(d.get('client_sale_net_clp')):>10}  "
            f"{_fmt_clp(gross):>10}  "
            f"{_fmt_supplier_paid(d.get('supplier_amount_paid_decimal'), d.get('supplier_amount_paid_minor')):<10}  "
            f"{_truncate(str(d.get('freight_status') or '—'), 28):<28}  "
            f"{str(d.get('updated_at') or '—')}"
        )
    lines.append(f"\n({len(deals)} deal(s))")
    return "\n".join(lines)


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def deal_list_to_json_payload(deals: list[dict[str, Any]]) -> dict[str, Any]:
    return {"count": len(deals), "deals": deals}
