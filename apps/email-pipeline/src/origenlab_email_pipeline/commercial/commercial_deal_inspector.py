"""Read-only inspection of a single commercial deal from SQLite.

Returns a structured DealReport dict; formatting is the caller's concern.
Never writes to SQLite, never prints email bodies or full attachment text.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_MASKED = "***MASKED***"

_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "transfer_id",
        "operation_id",
        "bank_account",
        "rut",
        "iban",
        "bic",
    }
)

_FORBIDDEN_COLUMN_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "body",
        "full_body",
        "body_clean",
        "body_text",
        "attachment_extract",
        "full_text",
    }
)

_MARGIN_BLOCKERS: dict[str, str] = {
    "needs_review": (
        "Margin not yet computed — waiting for: Wise CLP debit amount (card settlement "
        "vs. wire), DHL/logistics CLP cost, and any import duties. "
        "Run margin computation once those costs are confirmed."
    ),
    "not_computed": "Margin computation has not been run for this deal.",
    "blocked": "Margin computation is explicitly blocked — check notes_json on the deal row.",
}


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite file not found: {resolved}")
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row)))


def _mask_sensitive(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in d.items():
        if key in _SENSITIVE_FIELDS:
            out[key] = _MASKED if value else None
        elif any(sub in key.lower() for sub in _FORBIDDEN_COLUMN_SUBSTRINGS):
            continue
        else:
            out[key] = value
    return out


def _mask_payment_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in _SENSITIVE_FIELDS:
            out[key] = _MASKED if value else None
        elif any(sub in key.lower() for sub in _FORBIDDEN_COLUMN_SUBSTRINGS):
            continue
        elif key == "transfer_id" and value:
            out[key] = _MASKED
        elif key == "operation_id" and value:
            out[key] = _MASKED
        else:
            out[key] = value
    return out


def fetch_deal_header(conn: sqlite3.Connection, deal_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            id, deal_key, title, deal_status, margin_status,
            reconciliation_status, freight_status,
            client_org_name, client_domain, client_contact_email,
            client_po_number, client_invoice_number,
            supplier_org_name, supplier_domain, supplier_contact_email,
            supplier_customer_code, supplier_po_number, supplier_invoice_number,
            client_sale_net_clp, client_iva_amount_clp, client_iva_rate,
            client_sale_gross_clp, client_payment_received_clp,
            supplier_invoice_total_decimal, supplier_invoice_total_minor,
            supplier_amount_paid_decimal, supplier_amount_paid_minor,
            schema_version, confidence, notes_json,
            created_at, updated_at
        FROM commercial_deal
        WHERE deal_key = ?
        LIMIT 1
        """,
        (deal_key,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def fetch_lines(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            l.line_number, l.side, l.line_kind, l.ref_code, l.description,
            l.brand, l.quantity, l.currency,
            l.line_net_amount, l.line_amount_decimal, l.confidence,
            p.name AS product_name
        FROM commercial_deal_line l
        LEFT JOIN commercial_product p ON p.id = l.product_id
        WHERE l.deal_id = ?
        ORDER BY l.side, l.line_number
        """,
        (deal_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def fetch_costs(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            cost_kind, description, currency,
            amount_decimal, amount_minor,
            excluded_from_supplier_wire, is_estimated, confidence
        FROM commercial_deal_cost
        WHERE deal_id = ?
        ORDER BY cost_kind
        """,
        (deal_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def fetch_payments(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            direction, payment_method, paid_at, currency,
            amount_gross_integer, amount_net_integer, iva_amount_integer,
            amount_decimal, amount_minor,
            secondary_currency, secondary_amount_decimal, secondary_amount_minor,
            transfer_id, operation_id,
            counterparty_email, subject, confidence
        FROM commercial_deal_payment
        WHERE deal_id = ?
        ORDER BY paid_at, direction
        """,
        (deal_id,),
    ).fetchall()
    return [_mask_payment_row(_row_to_dict(r)) for r in rows]


import re as _re

_TRANSFER_ID_PATTERN = _re.compile(r"\b(transfer|ref|op|id)\s+(\d{8,20})\b", _re.IGNORECASE)
_STANDALONE_NUMERIC_ID_PATTERN = _re.compile(r"(?<![a-zA-Z])\d{8,20}(?![a-zA-Z\d])")


def _scrub_event_summary(summary: str | None) -> str | None:
    """Replace raw numeric transfer/operation IDs in event summaries."""
    if not summary:
        return summary
    return _TRANSFER_ID_PATTERN.sub(
        lambda m: f"{m.group(1)} {_MASKED}",
        summary,
    )


def fetch_events(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_at, event_type, summary, actor_email,
               counterparty_email, confidence
        FROM commercial_deal_event
        WHERE deal_id = ?
        ORDER BY event_at
        """,
        (deal_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["summary"] = _scrub_event_summary(d.get("summary"))
        out.append(d)
    return out


def fetch_field_evidence(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT field_name, normalized_value, extracted_value,
               parser_name, operator_confirmed, confidence
        FROM commercial_deal_field_evidence
        WHERE deal_id = ?
        ORDER BY field_name
        """,
        (deal_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _scrub_payment_ref_doc(d: dict[str, Any]) -> dict[str, Any]:
    """Mask raw long numeric IDs in doc_number and filename for payment vouchers."""
    if d.get("document_type") != "payment_voucher":
        return d
    out = dict(d)
    doc_num = str(out.get("doc_number") or "")
    if _STANDALONE_NUMERIC_ID_PATTERN.fullmatch(doc_num.strip()):
        out["doc_number"] = _MASKED
    filename = str(out.get("filename") or "")
    out["filename"] = _STANDALONE_NUMERIC_ID_PATTERN.sub(_MASKED, filename)
    return out


def fetch_documents(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT document_type, doc_number, filename,
               issued_at, currency, amount_decimal, confidence
        FROM commercial_deal_document
        WHERE deal_id = ?
        ORDER BY document_type
        """,
        (deal_id,),
    ).fetchall()
    return [_scrub_payment_ref_doc(_row_to_dict(r)) for r in rows]


def fetch_review(conn: sqlite3.Connection, deal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT reviewer, outcome, reason_code, reason_text,
               fields_reviewed_json, created_at
        FROM commercial_deal_review
        WHERE deal_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (deal_id,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def margin_blocker_explanation(margin_status: str) -> str:
    return _MARGIN_BLOCKERS.get(
        margin_status,
        f"Margin status {margin_status!r} — no standard explanation available.",
    )


def build_deal_report(conn: sqlite3.Connection, deal_key: str) -> dict[str, Any]:
    header = fetch_deal_header(conn, deal_key)
    if header is None:
        raise KeyError(f"deal not found: {deal_key!r}")
    deal_id = int(header["id"])
    return {
        "deal_key": deal_key,
        "header": header,
        "lines": fetch_lines(conn, deal_id),
        "costs": fetch_costs(conn, deal_id),
        "payments": fetch_payments(conn, deal_id),
        "events": fetch_events(conn, deal_id),
        "field_evidence": fetch_field_evidence(conn, deal_id),
        "documents": fetch_documents(conn, deal_id),
        "review": fetch_review(conn, deal_id),
        "margin_blocker_explanation": margin_blocker_explanation(str(header.get("margin_status", ""))),
    }


# ---------------------------------------------------------------------------
# Human-readable formatting
# ---------------------------------------------------------------------------

def _fmt_clp(value: int | None) -> str:
    if value is None:
        return "—"
    return f"CLP {value:,}"


def _fmt_decimal(value: str | None, currency: str | None, minor: int | None) -> str:
    if not value:
        return "—"
    cur = (currency or "").upper()
    if minor is not None:
        return f"{cur} {value} ({minor} minor)"
    return f"{cur} {value}"


def _sep(width: int = 72, char: str = "─") -> str:
    return char * width


def format_deal_report(report: dict[str, Any]) -> str:
    h = report["header"]
    lines_out: list[str] = []
    a = lines_out.append

    a(_sep(72, "═"))
    a(f"  COMMERCIAL DEAL INSPECTION  |  {h['deal_key']}")
    a(_sep(72, "═"))

    a("")
    a("── DEAL HEADER " + "─" * 58)
    a(f"  Title              : {h.get('title') or '—'}")
    a(f"  Status             : {h.get('deal_status')}")
    a(f"  Margin status      : {h.get('margin_status')}")
    a(f"  Reconciliation     : {h.get('reconciliation_status')}")
    a(f"  Freight status     : {h.get('freight_status')}")
    a(f"  Schema version     : {h.get('schema_version')}")
    a(f"  Confidence         : {h.get('confidence')}")
    a(f"  Created            : {h.get('created_at')}")

    a("")
    a("── CLIENT " + "─" * 63)
    a(f"  Org                : {h.get('client_org_name')}")
    a(f"  Domain             : {h.get('client_domain')}")
    a(f"  Contact email      : {h.get('client_contact_email')}")
    a(f"  PO number          : {h.get('client_po_number')}")
    a(f"  Invoice number     : {h.get('client_invoice_number')}")

    a("")
    a("── SUPPLIER " + "─" * 61)
    a(f"  Org                : {h.get('supplier_org_name')}")
    a(f"  Domain             : {h.get('supplier_domain')}")
    a(f"  Contact email      : {h.get('supplier_contact_email')}")
    a(f"  Customer code      : {h.get('supplier_customer_code')}")
    a(f"  PO number          : {h.get('supplier_po_number')}")
    a(f"  Invoice / proforma : {h.get('supplier_invoice_number')}")

    a("")
    a("── CLIENT SALE " + "─" * 58)
    a(f"  Net (ex-IVA)       : {_fmt_clp(h.get('client_sale_net_clp'))}")
    iva_rate = h.get("client_iva_rate")
    iva_pct = f"  ({int(round(iva_rate * 100))}%)" if iva_rate else ""
    a(f"  IVA                : {_fmt_clp(h.get('client_iva_amount_clp'))}{iva_pct}")
    a(f"  Gross / payment    : {_fmt_clp(h.get('client_sale_gross_clp'))}")
    a(f"  Received           : {_fmt_clp(h.get('client_payment_received_clp'))}")

    a("")
    a("── SUPPLIER INVOICE TOTALS " + "─" * 46)
    a(
        "  Invoice total      : "
        + _fmt_decimal(
            h.get("supplier_invoice_total_decimal"),
            "EUR",
            h.get("supplier_invoice_total_minor"),
        )
    )
    a(
        "  Amount paid        : "
        + _fmt_decimal(
            h.get("supplier_amount_paid_decimal"),
            "EUR",
            h.get("supplier_amount_paid_minor"),
        )
    )

    lines = report.get("lines") or []
    if lines:
        a("")
        a("── CLIENT LINES " + "─" * 57)
        for ln in lines:
            amt = _fmt_clp(ln.get("line_net_amount"))
            ref = ln.get("ref_code") or "—"
            desc = ln.get("description") or "—"
            qty = ln.get("quantity") or "1"
            a(f"  [{ln.get('line_number'):>2}] {ref:<12}  {desc:<40}  qty={qty}  net={amt}")

    costs = report.get("costs") or []
    if costs:
        a("")
        a("── SUPPLIER COSTS " + "─" * 55)
        for c in costs:
            excl = "  [excl. from wire]" if c.get("excluded_from_supplier_wire") else ""
            est = "  [estimated]" if c.get("is_estimated") else ""
            a(
                f"  {c['cost_kind']:<30}  "
                f"{_fmt_decimal(c.get('amount_decimal'), c.get('currency'), c.get('amount_minor'))}"
                f"{excl}{est}"
            )

    payments = report.get("payments") or []
    if payments:
        a("")
        a("── PAYMENTS " + "─" * 61)
        for p in payments:
            direction = (p.get("direction") or "").upper()
            method = p.get("payment_method") or "—"
            at = (p.get("paid_at") or "—")[:19]
            cur = p.get("currency") or ""
            if cur == "CLP":
                amt = _fmt_clp(p.get("amount_gross_integer"))
            else:
                amt = _fmt_decimal(p.get("amount_decimal"), cur, p.get("amount_minor"))
            secondary = ""
            if p.get("secondary_currency"):
                secondary = (
                    "  + "
                    + _fmt_decimal(
                        p.get("secondary_amount_decimal"),
                        p.get("secondary_currency"),
                        p.get("secondary_amount_minor"),
                    )
                )
            subject = f"  subj={p['subject']!r}" if p.get("subject") else ""
            tid = f"  transfer_id={p['transfer_id']}" if p.get("transfer_id") else ""
            a(f"  {direction:<10} {method:<16}  {at}  {amt}{secondary}{subject}{tid}")

    events = report.get("events") or []
    if events:
        a("")
        a("── EVENTS TIMELINE " + "─" * 53)
        for ev in events:
            at = (ev.get("event_at") or "—")[:19]
            etype = ev.get("event_type") or "—"
            summary = ev.get("summary") or ""
            a(f"  {at}  {etype:<35}  {summary}")

    field_ev = report.get("field_evidence") or []
    if field_ev:
        a("")
        a("── FIELD EVIDENCE " + "─" * 54)
        for fe in field_ev:
            confirmed = "✓" if fe.get("operator_confirmed") else " "
            a(
                f"  [{confirmed}] {fe.get('field_name'):<40}  "
                f"{str(fe.get('normalized_value') or '—'):<20}  "
                f"{fe.get('confidence') or '—'}"
            )

    docs = report.get("documents") or []
    if docs:
        a("")
        a("── DOCUMENTS " + "─" * 59)
        for d in docs:
            num = d.get("doc_number") or "—"
            fn = d.get("filename") or "—"
            amt = ""
            if d.get("amount_decimal"):
                amt = f"  {_fmt_decimal(d.get('amount_decimal'), d.get('currency'), None)}"
            a(f"  {d.get('document_type'):<22}  #{num:<20}  {fn}{amt}")

    review = report.get("review")
    if review:
        a("")
        a("── REVIEW " + "─" * 62)
        a(f"  Reviewer           : {review.get('reviewer')}")
        a(f"  Outcome            : {review.get('outcome')}")
        a(f"  Reason code        : {review.get('reason_code')}")
        a(f"  Reason text        : {review.get('reason_text')}")
        a(f"  Created            : {review.get('created_at')}")

    margin_status = str(h.get("margin_status") or "")
    if margin_status in ("needs_review", "not_computed", "blocked"):
        a("")
        a("── MARGIN BLOCKERS " + "─" * 53)
        a(f"  Status: {margin_status}")
        for part in report.get("margin_blocker_explanation", "").split("."):
            part = part.strip()
            if part:
                a(f"  {part}.")

    a("")
    a(_sep(72, "═"))
    return "\n".join(lines_out)
