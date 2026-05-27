"""Product catalogue SQLite DDL (Phase 8B).

See docs/catalog/PRODUCT_CATALOG_SCHEMA_AUDIT_V1.md.
"""

from __future__ import annotations

import sqlite3

CATALOG_SCHEMA_VERSION = "1.0.0"

PRODUCT_KINDS: tuple[str, ...] = (
    "equipment",
    "consumable",
    "reagent",
    "accessory",
    "service",
)

CONFIDENCE_LEVELS: tuple[str, ...] = (
    "operator_confirmed",
    "website_editorial",
    "extracted_needs_review",
    "extracted_high",
    "extracted_low",
)

OFFER_STATUSES: tuple[str, ...] = (
    "received",
    "valid",
    "expired",
    "superseded",
    "needs_review",
)

SNAPSHOT_KINDS: tuple[str, ...] = (
    "supplier_quote",
    "client_quote",
    "deal_line",
    "website_list",
)

LINK_KINDS: tuple[str, ...] = (
    "commercial_deal_line",
    "warm_case",
    "equipment_opportunity",
    "website_product",
    "purchase_event_item",
)

CATALOG_TABLE_NAMES: tuple[str, ...] = (
    "catalog_product",
    "catalog_product_alias",
    "catalog_product_category",
    "catalog_product_category_map",
    "catalog_product_spec",
    "catalog_supplier_offer",
    "catalog_price_snapshot",
    "catalog_product_commercial_link",
)

CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS catalog_product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_key TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  brand TEXT,
  manufacturer_name TEXT,
  product_kind TEXT NOT NULL,
  equipment_class TEXT,
  model_number TEXT,
  default_unit TEXT,
  website_slug TEXT,
  website_product_id TEXT,
  public_summary TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  confidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_product_brand ON catalog_product(brand);
CREATE INDEX IF NOT EXISTS idx_catalog_product_equipment_class ON catalog_product(equipment_class);
CREATE INDEX IF NOT EXISTS idx_catalog_product_website_slug ON catalog_product(website_slug);

CREATE TABLE IF NOT EXISTS catalog_product_alias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  alias_code TEXT NOT NULL,
  alias_source TEXT NOT NULL,
  alias_kind TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(alias_source, alias_code)
);
CREATE INDEX IF NOT EXISTS idx_catalog_product_alias_product ON catalog_product_alias(product_id);

CREATE TABLE IF NOT EXISTS catalog_product_category (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_key TEXT NOT NULL UNIQUE,
  parent_category_key TEXT,
  display_name TEXT NOT NULL,
  equipment_class TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_product_category_map (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL REFERENCES catalog_product_category(id) ON DELETE CASCADE,
  is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
  created_at TEXT NOT NULL,
  UNIQUE(product_id, category_id)
);
CREATE INDEX IF NOT EXISTS idx_catalog_category_map_category ON catalog_product_category_map(category_id);

CREATE TABLE IF NOT EXISTS catalog_product_spec (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  spec_group TEXT,
  spec_key TEXT NOT NULL,
  spec_value TEXT NOT NULL,
  spec_value_numeric REAL,
  spec_unit TEXT,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(product_id, spec_key, source)
);
CREATE INDEX IF NOT EXISTS idx_catalog_product_spec_product ON catalog_product_spec(product_id);

CREATE TABLE IF NOT EXISTS catalog_supplier_offer (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_key TEXT NOT NULL UNIQUE,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  supplier_org_name TEXT,
  supplier_domain TEXT,
  offer_status TEXT NOT NULL,
  quoted_at TEXT,
  valid_until TEXT,
  incoterm TEXT,
  payment_terms TEXT,
  delivery_terms TEXT,
  currency TEXT,
  quantity_offered TEXT,
  availability_note TEXT,
  evidence_email_id INTEGER,
  evidence_attachment_id INTEGER,
  confidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_supplier_offer_product ON catalog_supplier_offer(product_id);

CREATE TABLE IF NOT EXISTS catalog_price_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_key TEXT NOT NULL UNIQUE,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  supplier_offer_id INTEGER REFERENCES catalog_supplier_offer(id) ON DELETE SET NULL,
  snapshot_kind TEXT NOT NULL,
  currency TEXT,
  amount_decimal TEXT,
  amount_minor INTEGER,
  amount_clp_integer INTEGER,
  quantity TEXT,
  unit TEXT,
  incoterm TEXT,
  price_notes TEXT,
  is_public_safe INTEGER NOT NULL DEFAULT 0 CHECK (is_public_safe IN (0, 1)),
  confidence TEXT NOT NULL,
  observed_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_price_snapshot_product ON catalog_price_snapshot(product_id);

CREATE TABLE IF NOT EXISTS catalog_product_commercial_link (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,
  link_kind TEXT NOT NULL,
  link_ref TEXT NOT NULL,
  confidence TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(link_kind, link_ref)
);
CREATE INDEX IF NOT EXISTS idx_catalog_commercial_link_product ON catalog_product_commercial_link(product_id);
"""


def catalog_tables_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_product' LIMIT 1"
    ).fetchone()
    return row is not None


def ensure_catalog_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CATALOG_DDL)
    conn.commit()


def foreign_key_check_ok(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    return len(rows) == 0
