# Commercial deal ledger — Phase 3 apply log

Operator apply of schema **v1.1.0** and SERVA→CEAF promotion to the local operational SQLite database.

## Apply metadata

| Field | Value |
|-------|-------|
| Date/time | **2026-05-26** |
| Target DB | `/home/rafael/data/origenlab-email/sqlite/emails.sqlite` |
| Backup (rollback) | `/home/rafael/data/origenlab-email/sqlite/backups/emails-20260526T163109Z.sqlite` |
| Deal key | `serva-ceaf-oc-26172-po-174-26` |
| Schema version | **1.1.0** |

## Schema apply

- **Tables created:** 11 commercial ledger tables (`commercial_product`, `commercial_product_alias`, `commercial_deal`, `commercial_deal_evidence`, `commercial_deal_document`, `commercial_deal_payment`, `commercial_deal_line`, `commercial_deal_cost`, `commercial_deal_event`, `commercial_deal_field_evidence`, `commercial_deal_review`)
- **DDL mode:** additive `CREATE IF NOT EXISTS` only (no drops, no data migration from legacy `commercial_purchase_*`)

## Promotion apply

| Run | Result |
|-----|--------|
| First | **insert** |
| Second | **update** (idempotency verified — no duplicate deal or child rows) |

### Row counts (after apply)

| Table | Count |
|-------|------:|
| `commercial_deal` | 1 |
| `commercial_deal_evidence` | 15 |
| `commercial_deal_document` | 4 |
| `commercial_deal_payment` | 2 |
| `commercial_deal_line` | 3 |
| `commercial_deal_cost` | 3 |
| `commercial_deal_event` | 7 |
| `commercial_deal_field_evidence` | 7 |
| `commercial_deal_review` | 1 |
| `commercial_product` | 2 |
| `commercial_product_alias` | 4 |

Deal header (expected): `deal_status=logistics_pending`, `margin_status=needs_review`, `reconciliation_status=reconciled_excluding_supplier_freight`.

## Integrity checks

| When | `PRAGMA integrity_check` |
|------|-------------------------|
| Before apply | **ok** |
| After apply | **ok** |

## Safety scope (confirmed)

- No Gmail mutation
- No sends
- No outreach writes
- No mart rebuild
- No Postgres sync or migration
- No Render deploy
- No API or dashboard exposure of commercial deal ledger

## Rollback

If Phase 3 must be undone, restore the timestamped backup over the operational file (stop writers first):

```bash
cp -a /home/rafael/data/origenlab-email/sqlite/backups/emails-20260526T163109Z.sqlite \
      /home/rafael/data/origenlab-email/sqlite/emails.sqlite

sqlite3 /home/rafael/data/origenlab-email/sqlite/emails.sqlite "PRAGMA integrity_check;"
```

Expect `ok`. The 11 `commercial_*` tables created in Phase 3 will remain in the restored file unless the backup was taken **before** schema apply; this backup was taken **before** Phase 3 mutations, so rollback removes schema and promotion changes.

## Related docs

- [`COMMERCIAL_DEAL_LEDGER_SCHEMA_V1.md`](COMMERCIAL_DEAL_LEDGER_SCHEMA_V1.md) — canonical schema
- [`COMMERCIAL_DEAL_LEDGER_AUDIT.md`](COMMERCIAL_DEAL_LEDGER_AUDIT.md) — pre-ledger audit
