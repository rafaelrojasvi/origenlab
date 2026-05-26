"""Commercial deal ledger — SQLite DDL (schema v1.1.0).

See docs/commercial/COMMERCIAL_DEAL_LEDGER_SCHEMA_V1.md.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, ROUND_HALF_UP

COMMERCIAL_DEAL_SCHEMA_VERSION = "1.1.0"

DEAL_STATUSES: tuple[str, ...] = (
    "draft",
    "quoted",
    "client_po_received",
    "client_invoiced",
    "client_paid",
    "supplier_po_sent",
    "supplier_invoiced",
    "supplier_paid",
    "logistics_pending",
    "in_transit",
    "delivered",
    "closed",
    "cancelled",
    "needs_review",
)

MARGIN_STATUSES: tuple[str, ...] = (
    "not_computed",
    "needs_review",
    "computed",
    "blocked",
)

RECONCILIATION_STATUSES: tuple[str, ...] = (
    "not_applicable",
    "pending",
    "reconciled_excluding_supplier_freight",
    "reconciled_full",
    "mismatch",
    "needs_review",
)

FREIGHT_STATUSES: tuple[str, ...] = (
    "not_applicable",
    "quoted_on_supplier_invoice",
    "dhl_account_or_external_freight",
    "included_in_supplier_payment",
    "delivered",
    "needs_review",
)

LINE_SIDES: tuple[str, ...] = ("client", "supplier")

LINE_KINDS: tuple[str, ...] = ("product", "shipping", "handling", "discount", "other")

COST_KINDS: tuple[str, ...] = (
    "supplier_product",
    "supplier_handling",
    "supplier_freight_quoted",
    "logistics_dhl",
    "logistics_import",
    "bank_fee",
    "fx_spread",
    "other",
)

PAYMENT_DIRECTIONS: tuple[str, ...] = ("inbound", "outbound")

PAYMENT_METHODS: tuple[str, ...] = (
    "bank_transfer",
    "wise",
    "card",
    "check",
    "other",
)

DOCUMENT_TYPES: tuple[str, ...] = (
    "client_po",
    "client_quote",
    "client_invoice",
    "supplier_po",
    "supplier_proforma",
    "supplier_invoice",
    "payment_voucher",
    "payment_confirmation",
    "logistics_doc",
    "other",
)

EVENT_TYPES: tuple[str, ...] = (
    "deal_created",
    "client_quote_sent",
    "client_po_received",
    "client_invoice_sent",
    "client_payment_received",
    "client_bank_details_requested",
    "supplier_po_sent",
    "supplier_invoice_received",
    "supplier_payment_sent",
    "supplier_payment_confirmed",
    "logistics_pending",
    "shipment_released",
    "delivery_estimate_communicated",
    "delivered",
    "deal_closed",
    "deal_cancelled",
    "margin_review_requested",
    "note",
)

CONFIDENCE_LEVELS: tuple[str, ...] = (
    "operator_confirmed",
    "extracted_high",
    "extracted_low",
    "needs_review",
)

REVIEW_OUTCOMES: tuple[str, ...] = (
    "approved",
    "rejected",
    "needs_more_evidence",
    "snoozed",
)

COMMERCIAL_DEAL_TABLE_NAMES: tuple[str, ...] = (
    "commercial_product",
    "commercial_product_alias",
    "commercial_deal",
    "commercial_deal_evidence",
    "commercial_deal_document",
    "commercial_deal_payment",
    "commercial_deal_line",
    "commercial_deal_cost",
    "commercial_deal_event",
    "commercial_deal_field_evidence",
    "commercial_deal_review",
)

OPERATOR_ONLY_PAYMENT_COLUMNS: frozenset[str] = frozenset({"transfer_id", "operation_id"})

_DECIMAL_CURRENCIES: frozenset[str] = frozenset({"EUR", "USD"})

_FORBIDDEN_BODY_COLUMN_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "body",
        "full_body",
        "body_clean",
        "body_text",
        "attachment_extract",
        "full_text",
    }
)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _check(column: str, values: tuple[str, ...]) -> str:
    return f"CHECK ({column} IN ({_in_list(values)}))"


def _build_ddl() -> str:
    ck_deal_status = _check("deal_status", DEAL_STATUSES)
    ck_margin = _check("margin_status", MARGIN_STATUSES)
    ck_recon = _check("reconciliation_status", RECONCILIATION_STATUSES)
    ck_freight = _check("freight_status", FREIGHT_STATUSES)
    ck_side = _check("side", LINE_SIDES)
    ck_line_kind = _check("line_kind", LINE_KINDS)
    ck_cost_kind = _check("cost_kind", COST_KINDS)
    ck_direction = _check("direction", PAYMENT_DIRECTIONS)
    ck_pay_method = (
        "CHECK (payment_method IS NULL OR payment_method IN (" + _in_list(PAYMENT_METHODS) + "))"
    )
    ck_doc_type = _check("document_type", DOCUMENT_TYPES)
    ck_event_type = _check("event_type", EVENT_TYPES)
    ck_confidence = _check("confidence", CONFIDENCE_LEVELS)
    ck_review = _check("outcome", REVIEW_OUTCOMES)

    return f"""
CREATE TABLE IF NOT EXISTS commercial_product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ref_code TEXT NOT NULL UNIQUE,
  brand TEXT,
  name TEXT NOT NULL,
  category TEXT,
  subcategory TEXT,
  is_hazardous INTEGER NOT NULL DEFAULT 0 CHECK (is_hazardous IN (0, 1)),
  requires_special_shipping INTEGER NOT NULL DEFAULT 0 CHECK (requires_special_shipping IN (0, 1)),
  unit TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commercial_product_alias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES commercial_product(id) ON DELETE CASCADE,
  alias_code TEXT NOT NULL,
  alias_source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(alias_source, alias_code)
);
CREATE INDEX IF NOT EXISTS idx_commercial_product_alias_product
  ON commercial_product_alias(product_id);

CREATE TABLE IF NOT EXISTS commercial_deal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_key TEXT NOT NULL UNIQUE,
  title TEXT,
  deal_status TEXT NOT NULL,
  margin_status TEXT NOT NULL DEFAULT 'not_computed',
  reconciliation_status TEXT,
  freight_status TEXT,
  client_org_name TEXT NOT NULL,
  client_domain TEXT,
  client_contact_email TEXT,
  client_po_number TEXT,
  client_invoice_number TEXT,
  client_quote_number TEXT,
  client_project_code TEXT,
  supplier_org_name TEXT,
  supplier_domain TEXT,
  supplier_contact_email TEXT,
  supplier_customer_code TEXT,
  supplier_po_number TEXT,
  supplier_invoice_number TEXT,
  client_sale_net_clp INTEGER,
  client_iva_amount_clp INTEGER,
  client_iva_rate REAL,
  client_sale_gross_clp INTEGER,
  client_payment_received_clp INTEGER,
  supplier_invoice_total_decimal TEXT,
  supplier_invoice_total_minor INTEGER,
  supplier_amount_paid_decimal TEXT,
  supplier_amount_paid_minor INTEGER,
  schema_version TEXT NOT NULL,
  source_preview_path TEXT,
  source_preview_sha256 TEXT,
  parser_version TEXT,
  confirmed_facts_version TEXT,
  margin_net_clp INTEGER,
  margin_computed_at TEXT,
  margin_notes TEXT,
  confidence TEXT NOT NULL DEFAULT 'needs_review',
  legacy_purchase_event_id INTEGER,
  notes_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  {ck_deal_status},
  {ck_margin},
  {ck_recon},
  {ck_freight},
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_deal_key ON commercial_deal(deal_key);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_status ON commercial_deal(deal_status);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_client_domain ON commercial_deal(client_domain);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_supplier_domain ON commercial_deal(supplier_domain);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_client_po ON commercial_deal(client_po_number);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_supplier_po ON commercial_deal(supplier_po_number);

CREATE TABLE IF NOT EXISTS commercial_deal_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  evidence_kind TEXT CHECK (evidence_kind IS NULL OR evidence_kind IN (
    'email', 'attachment', 'operator_note', 'preview_json'
  )),
  email_id INTEGER,
  attachment_id INTEGER,
  filename TEXT,
  email_subject TEXT,
  email_date_iso TEXT,
  extract_snippet TEXT,
  operator_note TEXT,
  source_path TEXT,
  confidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_evidence_deal ON commercial_deal_evidence(deal_id);

CREATE TABLE IF NOT EXISTS commercial_deal_document (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  document_type TEXT NOT NULL,
  doc_number TEXT,
  filename TEXT,
  issued_at TEXT,
  currency TEXT,
  amount_decimal TEXT,
  amount_minor INTEGER,
  source_email_id INTEGER,
  source_attachment_id INTEGER,
  extract_status TEXT,
  confidence TEXT NOT NULL,
  evidence_id INTEGER REFERENCES commercial_deal_evidence(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  {ck_doc_type},
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_document_deal ON commercial_deal_document(deal_id);

CREATE TABLE IF NOT EXISTS commercial_deal_payment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  direction TEXT NOT NULL,
  payment_method TEXT,
  paid_at TEXT,
  currency TEXT NOT NULL,
  amount_gross_integer INTEGER,
  amount_net_integer INTEGER,
  iva_amount_integer INTEGER,
  amount_decimal TEXT,
  amount_minor INTEGER,
  secondary_currency TEXT,
  secondary_amount_decimal TEXT,
  secondary_amount_minor INTEGER,
  transfer_id TEXT,
  operation_id TEXT,
  counterparty_email TEXT,
  subject TEXT,
  confidence TEXT NOT NULL,
  evidence_id INTEGER REFERENCES commercial_deal_evidence(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  {ck_direction},
  {ck_pay_method},
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_payment_deal ON commercial_deal_payment(deal_id);

CREATE TABLE IF NOT EXISTS commercial_deal_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  line_number INTEGER NOT NULL,
  side TEXT NOT NULL,
  line_kind TEXT NOT NULL DEFAULT 'product',
  product_id INTEGER REFERENCES commercial_product(id) ON DELETE SET NULL,
  ref_code TEXT,
  description TEXT NOT NULL,
  brand TEXT,
  quantity TEXT,
  unit TEXT,
  currency TEXT NOT NULL,
  unit_amount_decimal TEXT,
  unit_amount_minor INTEGER,
  line_net_amount INTEGER,
  line_amount_decimal TEXT,
  line_amount_minor INTEGER,
  iva_rate REAL,
  iva_amount INTEGER,
  confidence TEXT NOT NULL,
  evidence_id INTEGER REFERENCES commercial_deal_evidence(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  {ck_side},
  {ck_line_kind},
  {ck_confidence},
  UNIQUE(deal_id, side, line_number)
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_line_deal_side
  ON commercial_deal_line(deal_id, side, line_number);

CREATE TABLE IF NOT EXISTS commercial_deal_cost (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  cost_kind TEXT NOT NULL,
  description TEXT,
  currency TEXT NOT NULL,
  amount_integer INTEGER,
  amount_decimal TEXT,
  amount_minor INTEGER,
  document_id INTEGER REFERENCES commercial_deal_document(id) ON DELETE SET NULL,
  payment_id INTEGER REFERENCES commercial_deal_payment(id) ON DELETE SET NULL,
  is_estimated INTEGER NOT NULL DEFAULT 0 CHECK (is_estimated IN (0, 1)),
  excluded_from_supplier_wire INTEGER NOT NULL DEFAULT 0 CHECK (excluded_from_supplier_wire IN (0, 1)),
  confidence TEXT NOT NULL,
  evidence_id INTEGER REFERENCES commercial_deal_evidence(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  {ck_cost_kind},
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_cost_deal ON commercial_deal_cost(deal_id);

CREATE TABLE IF NOT EXISTS commercial_deal_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_at TEXT NOT NULL,
  actor_email TEXT,
  counterparty_email TEXT,
  subject TEXT,
  summary TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  source_email_id INTEGER,
  source_attachment_id INTEGER,
  confidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  {ck_event_type},
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_event_deal_at
  ON commercial_deal_event(deal_id, event_at);

CREATE TABLE IF NOT EXISTS commercial_deal_field_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  entity_table TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  field_name TEXT NOT NULL,
  extracted_value TEXT,
  normalized_value TEXT,
  evidence_id INTEGER REFERENCES commercial_deal_evidence(id) ON DELETE SET NULL,
  confidence TEXT NOT NULL,
  parser_name TEXT,
  parser_version TEXT,
  operator_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (operator_confirmed IN (0, 1)),
  created_at TEXT NOT NULL,
  {ck_confidence}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_field_evidence_entity
  ON commercial_deal_field_evidence(deal_id, entity_table, entity_id);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_field_evidence_field
  ON commercial_deal_field_evidence(deal_id, field_name);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_field_evidence_evidence
  ON commercial_deal_field_evidence(evidence_id);

CREATE TABLE IF NOT EXISTS commercial_deal_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES commercial_deal(id) ON DELETE CASCADE,
  reviewer TEXT NOT NULL DEFAULT 'operator',
  outcome TEXT NOT NULL,
  reason_code TEXT,
  reason_text TEXT NOT NULL,
  fields_reviewed_json TEXT,
  schema_version TEXT,
  source_preview_path TEXT,
  source_preview_sha256 TEXT,
  parser_version TEXT,
  confirmed_facts_version TEXT,
  created_at TEXT NOT NULL,
  {ck_review}
);
CREATE INDEX IF NOT EXISTS idx_commercial_deal_review_deal ON commercial_deal_review(deal_id);
"""


COMMERCIAL_DEAL_DDL: str = _build_ddl()


def list_commercial_deal_tables() -> tuple[str, ...]:
    return COMMERCIAL_DEAL_TABLE_NAMES


def decimal_to_minor(amount: str, currency: str) -> int:
    """Convert decimal string to minor units for EUR/USD. CLP must use integer pesos elsewhere."""
    cur = (currency or "").strip().upper()
    if cur == "CLP":
        raise ValueError("CLP amounts must be stored as whole pesos (INTEGER), not decimal_to_minor")
    if cur not in _DECIMAL_CURRENCIES:
        raise ValueError(f"decimal_to_minor supports EUR/USD only, got {currency!r}")
    normalized = amount.strip().replace(",", ".")
    minor = (Decimal(normalized) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def minor_to_decimal(amount_minor: int, scale: int = 2) -> str:
    """Convert minor units back to decimal string (default 2 dp)."""
    if scale != 2:
        raise ValueError("only scale=2 supported in v1")
    whole = Decimal(amount_minor) / 100
    return format(whole.quantize(Decimal("0.01")), "f")


def validate_decimal_minor_pair(amount_decimal: str, amount_minor: int, currency: str) -> bool:
    try:
        return decimal_to_minor(amount_decimal, currency) == amount_minor
    except ValueError:
        return False


def count_commercial_deal_indexes(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'index'
          AND name NOT LIKE 'sqlite_%'
          AND (
            tbl_name LIKE 'commercial_deal%'
            OR tbl_name LIKE 'commercial_product%'
          )
        """
    ).fetchone()
    return int(row[0]) if row else 0


def foreign_key_check_ok(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    return len(rows) == 0


def table_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def ensure_commercial_deal_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(COMMERCIAL_DEAL_DDL)
    conn.commit()


def commercial_deal_tables_exist(conn: sqlite3.Connection) -> bool:
    for name in COMMERCIAL_DEAL_TABLE_NAMES:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        if not row:
            return False
    return True
