# Product catalogue — Phase 8B local seed + builder

**Status:** Implemented (2026-05-27). SQLite/local only — no Postgres, API, or dashboard.

Design reference: [`PRODUCT_CATALOG_SCHEMA_AUDIT_V1.md`](PRODUCT_CATALOG_SCHEMA_AUDIT_V1.md).

## Files

| Path | Role |
|------|------|
| `apps/email-pipeline/data/catalog/catalog_seed_v1.json` | Operator seed (9 products, categories, specs, offers, prices, links) |
| `apps/email-pipeline/scripts/catalog/build_catalog_sqlite.py` | CLI builder |
| `apps/email-pipeline/src/origenlab_email_pipeline/catalog/` | Schema, validation, upsert logic |

## SQLite tables

- `catalog_product`
- `catalog_product_alias`
- `catalog_product_category`
- `catalog_product_category_map`
- `catalog_product_spec`
- `catalog_supplier_offer`
- `catalog_price_snapshot`
- `catalog_product_commercial_link`

## Run (dry-run)

```bash
cd apps/email-pipeline
uv run python scripts/catalog/build_catalog_sqlite.py --dry-run
```

Validates seed JSON and prints row counts **without** modifying any database file.

## Run (apply to local SQLite)

Uses `ORIGENLAB_SQLITE_PATH` when set; otherwise `~/data/origenlab-email/sqlite/emails.sqlite`.

```bash
cd apps/email-pipeline
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"
uv run python scripts/catalog/build_catalog_sqlite.py
```

Idempotent: re-running updates products by `product_key` and refreshes child rows per product.

## Tests

```bash
cd apps/email-pipeline
uv run pytest tests/test_catalog_seed.py tests/test_build_catalog_sqlite.py -q
```

## Safety rules (enforced in seed validation)

- Supplier prices default `is_public_safe = false`.
- IKA RV10.70 price: `currency` null + explicit ambiguity note.
- Forbidden substrings rejected in safe fields: bank, SWIFT, IBAN, RUT, Gmail URLs, `transfer_id`, `operation_id`, etc.
- No email bodies, bank details, or evidence file paths in seed.

## Not in Phase 8B

- Postgres migration / mirror sync  
- `GET /mirror/catalog/*` API  
- Dashboard **Catálogo** page  
- Gmail ingest, sends, outreach, production deploy  

Next: **Phase 8C** — Postgres read mirror after design approval.
