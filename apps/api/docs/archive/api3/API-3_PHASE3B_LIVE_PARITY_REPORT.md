# API-3 Phase 3B — Live dual-server mirror parity report

**Date:** 2026-05 (automated run)  
**Disposable DB:** `postgresql+psycopg://origenlab:origenlab@127.0.0.1:5433/origenlab_api3_parity_test` (Docker `origenlab-api3-parity-pg`, Postgres 16)  
**SQLite:** `/tmp/origenlab-api3-parity/parity.sqlite` (minimal mart fixture; not production)

## Procedure

```bash
apps/api/scripts/run_mirror_dual_server_parity.sh
```

Steps: fresh Docker Postgres → Alembic `upgrade head` → `sync_dashboard_postgres_mirror.py` → legacy `:8000` + `apps/api` `:8001` (`ORIGENLAB_API_BACKEND=postgres`) → `mirror_parity_smoke.py` → `npm run smoke:mirror`.

## Results

| Check | Legacy :8000 | Mirror :8001 | Parity |
|-------|--------------|--------------|--------|
| `/health/dependencies` → `/mirror/health/dependencies` | 200 | 200 | Keys match |
| `/meta/dashboard-sync` → `/mirror/meta/dashboard-sync` | 200 | 200 | Keys match |
| `/dashboard/summary` → `/mirror/dashboard/summary` | 200 | 200 | Keys match |
| `/classification/summary` → `/mirror/classification/summary` | 200 | 200 | Keys match |
| `/classification/recent` → `/mirror/classification/recent` | 200 | 200 | Keys match |
| `/classification/actions` → `/mirror/classification/actions` | 200 | 200 | Keys match |
| `/commercial/purchase-events` → `/mirror/commercial/purchase-events` | 200 | 200 | Keys match |
| `/contacts` → `/mirror/contacts` | 200 | 200 | Keys match |
| `/organizations` → `/mirror/organizations` | 200 | 200 | Keys match |
| `/outbound/suppressions/emails` → `/mirror/outbound/suppressions/emails` | 200 | 200 | Keys match |
| `/outbound/contact-state` → `/mirror/outbound/contact-state` | 200 | 200 | Keys match |
| `/outbound/readiness` → `/mirror/outbound/readiness` | 200 | 200 | Keys match |

**Optional detail route** `/commercial/purchase-events/{id}`: skipped when no rows (legacy may 503 vs mirror 404); not in Phase 3B required list. Use `--skip-commercial-detail` in `mirror_parity_smoke.py`.

**Dashboard `npm run smoke:mirror`:** GET `/mirror/health/dependencies`, `/mirror/dashboard/summary`, `/mirror/meta/dashboard-sync`, `/mirror/classification/summary` — all 200 on `:8001`.

## Safety

- Legacy `apps/email-pipeline/src/origenlab_api` **not deleted**
- Dashboard Today operator routes **unchanged** (no `/mirror/*` in active client)
- **GET-only** — no write endpoints exercised
- Gmail / production SQLite / production-scratch Postgres **not used**
- Container removed on script exit; return daily ops to SQLite (`unset ORIGENLAB_API_BACKEND`)

## Re-run

```bash
export ORIGENLAB_TEST_POSTGRES_URL='postgresql+psycopg://origenlab:origenlab@127.0.0.1:5433/origenlab_api3_parity_test'
apps/api/scripts/run_mirror_dual_server_parity.sh
```
