# Product catalogue — Phase 8C Postgres mirror

**Status:** Implemented (2026-05-27). Redacted read model only — no API or dashboard yet.

## Prerequisites

1. Local SQLite catalogue built (Phase 8B):
   ```bash
   cd apps/email-pipeline
   uv run python scripts/catalog/build_catalog_sqlite.py
   ```
2. Alembic head includes `20260527_0019`:
   ```bash
   uv run alembic upgrade head
   ```

## Sync (replace `catalog.*` from SQLite)

```bash
cd apps/email-pipeline
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"
export ORIGENLAB_POSTGRES_URL="..."   # scratch/staging only unless explicitly approved

uv run python scripts/sync/sync_catalog_postgres_mirror.py --dry-run
uv run python scripts/sync/sync_catalog_postgres_mirror.py
```

## Verify

```bash
uv run python scripts/qa/verify_catalog_postgres_mirror.py --scan-text
```

Compares SQLite vs Postgres row counts and scans text columns for forbidden terms (bank, SWIFT, Gmail URLs, etc.).

## Postgres tables

- `catalog.product`
- `catalog.product_category`
- `catalog.product_alias`
- `catalog.product_category_map`
- `catalog.product_spec`
- `catalog.supplier_offer`
- `catalog.price_snapshot`
- `catalog.product_commercial_link`

**Not mirrored:** `evidence_email_id`, `evidence_attachment_id`, alias `notes`, email bodies, bank details.

## Tests

```bash
uv run pytest tests/test_catalog_seed.py tests/test_build_catalog_sqlite.py tests/test_catalog_postgres_mirror.py -q
```
