# OrigenLab API (`apps/api`)

> **Operator handoff (v1 freeze):** [../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md](../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md)

Read-only **operator API** over SQLite and `reports/out/active/current`. This app is separated from `apps/email-pipeline` so daily ingest, DNR refresh, and mutation CLIs stay unchanged.

## Package name collision (important)

Two Python trees use the name **`origenlab_api`**. Only one should be on `sys.path` for a given process.

| Location | Role |
|----------|------|
| **`apps/api/src/origenlab_api`** | **New separated operator API** (this app). API-0+ routes: `/health`, `/operator/status`, `/emails/recent`, … |
| **`apps/email-pipeline/src/origenlab_api`** | **Legacy / parked Postgres mirror API** (Slice 1). Still used by some email-pipeline tooling until Phase API-3 relocation. |

**Always run tests and uvicorn from `apps/api`:**

```bash
cd apps/api
uv sync --group dev
uv run pytest tests -q
uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8001
```

Running uvicorn from `apps/email-pipeline` imports the **legacy** package and a different app factory. Do not delete or rename the legacy tree until a focused API-3 refactor.

`tests/conftest.py` prepends `apps/api/src` to `sys.path`. `tests/test_import_guard.py` asserts `origenlab_api.main` loads from **`apps/api/src`**.

## Runtime truth

| Layer | Role |
|-------|------|
| **SQLite** (`ORIGENLAB_SQLITE_PATH`) | Authoritative for outbound safety, Sent memory, outreach sidecars |
| **This API** | GET-only HTTP for operators and (later) dashboard reads |
| **Postgres mirror** | **Parked / optional** — not required to run this app |
| **email-pipeline** | **Write path** — ingest, `refresh_outbound_safety_memory`, `mark_outreach_state`, mart rebuilds |

## What this API must **not** run

API-0 is **read-only**. The HTTP app does not invoke and must not grow imports for:

| Forbidden operation | Typical entrypoint (stay in email-pipeline) |
|---------------------|---------------------------------------------|
| Gmail ingest | `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` |
| Safety memory refresh | `scripts/qa/refresh_outbound_safety_memory.py` |
| Postgres dashboard sync | `scripts/sync/sync_dashboard_postgres_mirror.py` |
| Alembic migrations | `alembic upgrade` |
| Send email | `scripts/qa/send_inline_html_email_via_gmail_api.py` |
| Queue regeneration | `scripts/qa/build_equipment_first_operator_queue.py` |
| Outreach state writes | `scripts/leads/mark_outreach_state.py --apply` |

CI: `tests/test_no_write_policy.py` checks GET-only routes and scans `apps/api/src/origenlab_api` for forbidden script references.

## CORS

**Not enabled in API-0.** Local development uses direct `curl` or TestClient. When **`apps/dashboard`** is wired (Phase API-4), add explicit allowed origins (e.g. Vite `http://127.0.0.1:5173`) via `ORIGENLAB_API_CORS_ORIGINS` — do not use `allow_origins=["*"]` in production.

## Endpoints

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| GET | `/health` | API-0 | Liveness + `operator-sqlite-readonly` mode |
| GET | `/operator/status` | API-0 | Operator verdict (delegates to `operator_status_report`) |
| GET | `/emails/recent` | API-1 | Recent canonical Gmail rows (previews only; no body) |
| GET | `/cases/warm` | API-1.1 | Warm commercial case queue (previews; heuristic categories) |
| GET | `/opportunities/equipment` | API-1.2 | Canonical `equipment_first_operator_queue_*.csv` (manifest; no regenerate) |
| GET | `/contacts/{email}` | API-1.3 / **Dashboard-2** | Read-only contact profile (SQLite or postgres mirror); used by Today side panel |

OpenAPI: `/docs` when the server is running.

## Setup

```bash
cd apps/api
uv sync --group dev
```

Requires editable `../email-pipeline` (`origenlab-email-pipeline`). Business logic is imported from `origenlab_email_pipeline` — not duplicated here.

## Environment

| Variable | Default |
|----------|---------|
| `ORIGENLAB_SQLITE_PATH` | From email-pipeline `load_settings()` |
| `ORIGENLAB_ACTIVE_CURRENT` | `../email-pipeline/reports/out/active/current` |

Postgres URL is **not** required.

## Tests

```bash
cd apps/api
uv run pytest tests -q
```

## Dashboard v1–v2 backend matrix

Dashboard v1 + **Dashboard-2 contact drilldown** use **this app only** (`apps/api`), not the legacy email-pipeline API on port 8000.

| Backend | Env | Smoke |
|---------|-----|-------|
| SQLite (default) | `ORIGENLAB_API_BACKEND` unset or `sqlite` | `dashboard_v1_http_smoke.py --expect-backend sqlite` |
| Postgres mirror | `ORIGENLAB_API_BACKEND=postgres` + disposable `ORIGENLAB_POSTGRES_URL` | `--expect-backend postgres` |

`dashboard_v1_http_smoke.py` also calls **`GET /contacts/{email}`** (email from warm/equipment rows; skips with WARN if none).

Full procedure: [`../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md) · matrix detail: [`../dashboard/docs/BACKEND_MATRIX_VALIDATION.md`](../dashboard/docs/BACKEND_MATRIX_VALIDATION.md).

**Freeze validation:** SQLite and disposable Postgres (`:5433`, fresh DB) contact smokes **passed**. Gmail / production scratch Postgres not used.

```bash
# SQLite smoke (TestClient + contact route)
uv run python scripts/dashboard_v1_http_smoke.py --expect-backend sqlite

# Postgres smoke (disposable ORIGENLAB_POSTGRES_URL only)
ORIGENLAB_API_BACKEND=postgres ORIGENLAB_POSTGRES_URL='postgresql+psycopg://…@127.0.0.1:5433/origenlab_dashboard2_test' \
  uv run python scripts/dashboard_v1_http_smoke.py --expect-backend postgres
```

Dashboard HTTP smokes: `npm run smoke:contacts`, `EXPECT_BACKEND=postgres npm run smoke:contacts`, `npm run smoke:proxy` — see dashboard README.

**After postgres validation:** unset `ORIGENLAB_API_BACKEND` and postgres URLs; restart this app on SQLite (`ORIGENLAB_SQLITE_PATH` only).

**Legacy API:** `apps/email-pipeline/src/origenlab_api` (port 8000, `/dashboard/*`, `/classification/*`) remains for compatibility. Do **not** delete until API-3 relocation and a reference audit are complete.

## Coexistence roadmap

- **API-0** (this app): SQLite operator plane.
- **API-3** Phase 1 **complete**; Phase 2 **parity frozen**; Phase **3A** repoints operator docs/smokes to `:8001` `/mirror/*` (legacy `:8000` deprecated, not deleted). Dashboard Today still uses operator routes only. **Checklist:** [docs/API-3_PHASE2_PARITY_CHECKLIST.md](docs/API-3_PHASE2_PARITY_CHECKLIST.md). **Design:** [docs/API-3_PHASE1_MIRROR_ROUTE_DESIGN.md](docs/API-3_PHASE1_MIRROR_ROUTE_DESIGN.md). **Audit:** [docs/API-3_RELOCATION_AUDIT.md](docs/API-3_RELOCATION_AUDIT.md).

Mirror reporting smoke (GET only; requires this app on :8001 + disposable `ORIGENLAB_POSTGRES_URL`):

```bash
cd apps/dashboard && npm run smoke:mirror
```

Optional dual-server parity (legacy :8000 + mirror :8001 both running):

```bash
cd apps/api
uv run python scripts/mirror_parity_smoke.py \
  --legacy-base http://127.0.0.1:8000 \
  --mirror-base http://127.0.0.1:8001
```
- **API-4** (done for v1): Dashboard points at this app only.
