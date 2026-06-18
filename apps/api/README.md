# OrigenLab API (`apps/api`)

> **Operator handoff (v1 freeze):** [../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md](../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md)

Read-only **operator API** over SQLite and `reports/out/active/current`. This app is separated from `apps/email-pipeline` so daily ingest, DNR refresh, and mutation CLIs stay unchanged.

## Package layout

This app owns **`apps/api/src/origenlab_api`** (operator routes + `/mirror/*` Postgres reporting). The legacy email-pipeline FastAPI tree on port **8000** was **removed in API-3 Phase 6** — see [docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md](docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md).

**Always run tests and uvicorn from `apps/api`:**

```bash
cd apps/api
uv sync --group dev
uv run pytest tests -q
uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8001
```

`tests/conftest.py` prepends `apps/api/src` to `sys.path`. `tests/test_import_guard.py` asserts `origenlab_api.main` loads from **`apps/api/src`**.

## Runtime truth

| Layer | Role |
|-------|------|
| **SQLite** (`ORIGENLAB_SQLITE_PATH`) | Authoritative for outbound safety, Sent memory, outreach sidecars |
| **This API** | GET-only HTTP for **Dashboard Today** (`apps/dashboard`) and operator tooling |
| **Postgres mirror** | **Read-only reporting target** when `auto-mirror-dashboard` publishes; not send/outreach truth |
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

## CORS and production mode

**Dashboard v1** uses the **Vite proxy** in dev (no CORS needed). Production static dashboard calls the API directly — set:

| Variable | Production example |
|----------|-------------------|
| `ORIGENLAB_ENV` | `production` |
| `ORIGENLAB_API_BACKEND` | `postgres` |
| `ORIGENLAB_POSTGRES_URL` | Cloud Postgres DSN |
| `ORIGENLAB_API_CORS_ORIGINS` | `https://dashboard.origenlab.cl` (no `*`) |
| `ORIGENLAB_API_ALLOWED_HOSTS` | `api.origenlab.cl` (rejects raw `*.onrender.com` Host in production) |
| `ORIGENLAB_API_DISABLE_DOCS` | `true` (optional; docs also off when `ORIGENLAB_ENV=production`) |

CORS middleware allows **GET, HEAD, OPTIONS** only. See [`../email-pipeline/docs/PHASE1_CLOUD_READ_PATH.md`](../email-pipeline/docs/PHASE1_CLOUD_READ_PATH.md) and [`.env.production.example`](.env.production.example).

## Endpoints

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| GET | `/health` | API-0 | Liveness + `operator-sqlite-readonly` mode |
| GET | `/operator/status` | API-0 | Operator verdict (delegates to `operator_status_report`) |
| GET | `/operator/automation-status` | API-0 | Read-only automation health (mail auto-refresh + dashboard auto-mirror local state) |
| GET | `/emails/recent` | API-1 | Recent canonical Gmail rows (previews only; no body) |
| GET | `/cases/warm` | API-1.1 | Warm commercial case queue (previews; heuristic categories) |
| GET | `/opportunities/equipment` | API-1.2 | Equipment-first operator queue (**Postgres read model** in production; SQLite/CSV fallback dev-only) |

**Equipment read-model boundary:** production serves `api.v_equipment_opportunity` when `ORIGENLAB_API_BACKEND=postgres`. See [`../email-pipeline/docs/architecture/EQUIPMENT_READ_MODEL_BOUNDARY.md`](../email-pipeline/docs/architecture/EQUIPMENT_READ_MODEL_BOUNDARY.md).
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

Default local pre-PR check (frozen sync + full pytest, same shape as CI):

```bash
cd apps/api
./scripts/validate.sh
```

`./scripts/validate.sh` first runs a **Render-style no-dev runtime import smoke** (`uv sync --frozen --no-dev`, then imports `psycopg` and `origenlab_api.main` without Postgres or network). That catches missing runtime dependencies before production deploy. It then runs **`scripts/check_runtime_dependency_boundary.py`**, which inspects effective `uv tree --no-dev` and `uv tree --group dev` output and fails if ML-heavy packages (for example `torch`, `transformers`, `faiss-cpu`) appear in those trees.

**Runtime dependency boundary:** `apps/api` must remain ML-free at runtime and in dev test dependencies. Optional ML groups from `origenlab-email-pipeline` may still appear in `uv.lock`, but CI validates **effective** dependency trees — not raw lockfile entries — so Dependabot torch bumps are not merged blindly when they would enter the API install graph.

It then restores dev deps and runs the full pytest suite.

Targeted pytest is fine while developing; run `./scripts/validate.sh` before opening or merging API PRs. The validate script keeps both sync and test execution frozen so local validation does not rewrite `uv.lock`. `./scripts/validate.sh` runs tests in a deterministic SQLite-only mode, even if local `apps/api/.env` contains `ORIGENLAB_POSTGRES_URL` for mirror-page smoke testing.

```bash
cd apps/api
uv run pytest tests -q
```

### Inspect response shapes

For a human-readable snapshot of real `TestClient` responses against a minimal local fixture (no live server), run:

```bash
cd apps/api
uv run python scripts/audit_response_contract.py
```

The audit fails on contract violations including forbidden secret/path leaks (`/home/`, `/mnt/`, database URLs, etc.) anywhere in audited JSON responses. See [docs/API_RESPONSE_CONTRACT.md](docs/API_RESPONSE_CONTRACT.md).

Authenticated remote production audit (live API behind Cloudflare Access; skips with exit 0 when service token env vars are unset):

```bash
cd apps/api
CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... \
  uv run python scripts/remote_response_audit.py
```

Uses the same response contract checks as the local audit (`x-request-id`, JSON envelopes, list `meta`/`items`, forbidden path/secret leaks). Not part of `./scripts/validate.sh` (requires network + secrets).

GitHub Actions workflow: [`.github/workflows/api.yml`](../../.github/workflows/api.yml) runs `./scripts/validate.sh` for `apps/api` changes and `apps/email-pipeline` dependency changes.

### Render (native runtime)

| Setting | Value |
|---------|-------|
| `PYTHON_VERSION` | `3.12.11` |
| Build command | `uv sync --frozen --no-dev` |
| Start command | `uv run --no-sync uvicorn origenlab_api.main:app --host 0.0.0.0 --port ${PORT:-10000}` |

CI `./scripts/validate.sh` mirrors the build step with a no-dev import smoke before pytest.

### Remote production smoke

`./scripts/remote_smoke.sh` checks a deployed API (default `https://api.origenlab.cl`) behind Cloudflare Access.

Unauthenticated `GET /health` often returns **HTTP 302** to `cloudflareaccess.com` when Access is enabled — that is expected protection, not an API outage. Authenticated checks use Cloudflare **service tokens** (`CF-Access-Client-Id` / `CF-Access-Client-Secret` headers). Configure a **Service Auth** policy in Cloudflare Access for the token used by this script.

```bash
cd apps/api
./scripts/remote_smoke.sh
```

Protection-only (no production secrets; exits 0 after Check A):

```bash
cd apps/api
./scripts/remote_smoke.sh
```

Authenticated health (requires service token env vars):

```bash
cd apps/api
CF_ACCESS_CLIENT_ID=... \
CF_ACCESS_CLIENT_SECRET=... \
./scripts/remote_smoke.sh
```

Optional operator route (still read-only; adds `GET /operator/status`):

```bash
cd apps/api
ORIGENLAB_REMOTE_SMOKE_OPERATOR=1 \
CF_ACCESS_CLIENT_ID=... \
CF_ACCESS_CLIENT_SECRET=... \
./scripts/remote_smoke.sh
```

Override base URL for staging or local smoke:

```bash
ORIGENLAB_API_BASE_URL=http://127.0.0.1:8001 ./scripts/remote_smoke.sh
```

## Dashboard v1–v2 backend matrix

Dashboard v1 + **Dashboard-2 contact drilldown** use **this app only** (`apps/api` on port **8001**).

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

## API-3 mirror relocation (Phase 6 complete)

Postgres mirror reporting lives under **`GET /mirror/*`** on this app. Legacy email-pipeline `:8000` API **removed** — [docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md](docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md). **Strict gate:** `scripts/api3_phase6_grep_gate.sh`.

Mirror reporting smoke (GET only; requires this app on :8001 + disposable `ORIGENLAB_POSTGRES_URL`):

```bash
cd apps/dashboard && npm run smoke:mirror
```

**Live mirror smoke** (disposable Postgres on `:5433`; `:8001` only):

```bash
apps/api/scripts/run_mirror_dual_server_parity.sh
```

Report (historical): [docs/archive/api3/API-3_PHASE3B_LIVE_PARITY_REPORT.md](docs/archive/api3/API-3_PHASE3B_LIVE_PARITY_REPORT.md).

```bash
cd apps/api
uv run python scripts/mirror_parity_smoke.py --mirror-base http://127.0.0.1:8001
```
