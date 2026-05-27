# Lead research dashboard — Phase 10D

Read-only **Prospectos** view for Tatiana: DeepSearch / Phase 10B outputs → SQLite → Postgres `lead_intel.*` → API → dashboard.

## Architecture

```
Phase 10B CSV (review + blocked)
        ↓
build_lead_research_sqlite.py  →  SQLite lead_research_*  (source of truth)
        ↓
sync_lead_research_postgres_mirror.py  →  Postgres lead_intel.*  (redacted mirror)
        ↓
GET /mirror/leads/*  →  Dashboard #/prospectos
```

## Source of truth

- **SQLite** (`lead_research_batch`, `lead_research_prospect`, child tables) on the operational DB path (`ORIGENLAB_SQLITE_PATH`).
- **Postgres** `lead_intel` schema is a **read-only mirror** for the operator API/dashboard only.
- **No** Gmail sends, drafts, outreach state writes, or automatic contact approval.

## Schema (SQLite)

| Table | Purpose |
|-------|---------|
| `lead_research_batch` | Import batch metadata |
| `lead_research_prospect` | One row per organization/contact prospect |
| `lead_research_evidence` | Public evidence URLs |
| `lead_research_recommendation` | Suggested angle / preview (no send) |
| `lead_research_block_reason` | Block / risk codes |
| `lead_research_followup_candidate` | Optional follow-up queue from 10A.1 CSV |

Postgres mirror tables: `lead_intel.prospect`, `evidence`, `recommendation`, `block_reason`.

## Safety rules

Never exposed in mirror or API:

- Raw Gmail URLs, bodies, attachment IDs, operation/transfer IDs
- Source file paths, RUTs, bank details
- Internal `input_file_name` / `batch_key` in Postgres

Allowed: public evidence URLs, contact emails from public research (display only, **no send buttons**).

## Operator workflow (Tatiana)

1. Open **Hoy** → card **Prospectos nuevos** (net-new safe count).
2. Open **Prospectos** → filter by classification, sector, score.
3. Click a row → **Ficha del prospecto** drawer:
   - Net-new: review angle and suggested preview; human sends outside dashboard.
   - Same domain: warning to check prior conversation.
   - Public tender: technical equivalence route, not cold email.
   - Blocked: **No contactar**.
4. **Sistema** → **Lead intelligence** section shows mirror counts.

## Refresh / import new DeepSearch files

1. Run Phase 10B: `process_new_customer_research.py` (writes `new_customer_targets_*.csv` under `apps/email-pipeline/reports/out/active/current/`).
2. Build SQLite:
   ```bash
   cd apps/email-pipeline
   uv run python scripts/leads/build_lead_research_sqlite.py
   ```
3. Migrate + sync (requires Postgres):
   ```bash
   uv run alembic -c alembic.ini upgrade head
   uv run python scripts/sync/sync_lead_research_postgres_mirror.py
   uv run python scripts/qa/verify_lead_research_postgres_mirror.py --scan-text
   ```
4. Optional one-shot with dashboard refresh:
   ```bash
   RUN_LEAD_RESEARCH_MIRROR=1 bash apps/email-pipeline/scripts/ops/refresh_render_dashboard_once.sh
   ```
   Default: `RUN_LEAD_RESEARCH_MIRROR=0` (off).

## API (read-only)

- `GET /mirror/leads/prospects` — list + filters
- `GET /mirror/leads/prospects/{prospect_key}` — detail + evidence + recommendation
- `GET /mirror/leads/summary` — KPI counts

Alembic head after this phase: `20260528_0021`.
