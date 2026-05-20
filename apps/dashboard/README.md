# OrigenLab — Dashboard (React)

Read-only operator UI. **Dashboard v1 (Today)** talks only to **`apps/api`**:

- `GET /health`, `GET /operator/status` (operator panel)
- `GET /cases/warm`, `GET /opportunities/equipment` (read-only tables)

It does not open SQLite/Postgres, CSV files, or `apps/email-pipeline` modules from the browser.

Legacy commercial tabs (classification, compras, etc.) remain in the repo but are not mounted in v0 `App.tsx`.

## Dashboard v0 — Today / Operator Status

### Run with `apps/api`

**Terminal 1 — API** (from `apps/api`):

```bash
cd apps/api
uv sync
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"
# Optional Postgres mirror reads:
# export ORIGENLAB_API_BACKEND=postgres
# export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'

uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 — React** (from `apps/dashboard`):

```bash
npm install
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). In dev, Vite proxies `/health`, `/operator`, `/cases`, and `/opportunities` to the API (see `vite.config.ts`, default target port **8001**).

### Required env

| Variable | When | Purpose |
|----------|------|---------|
| `VITE_ORIGENLAB_API_BASE_URL` | **Required** for `npm run build` / production / preview | Public base URL of `apps/api` (no trailing slash), e.g. `https://api.example.com` |

**Production:** you **must** set `VITE_ORIGENLAB_API_BASE_URL` at build time. Production builds **throw at runtime** if it is missing (no silent `127.0.0.1` fallback).

**Development:** `npm run dev` uses the Vite proxy for `/health` and `/operator` only (same origin). Optional `VITE_ORIGENLAB_API_BASE_URL` changes the proxy target in `vite.config.ts` (default `http://127.0.0.1:8001`).

### Read-only scope

- **GET only** — no write/send/draft/archive buttons; row actions limited to copy contact text and optional `mailto:` links.
- **Send/outreach truth** stays in the SQLite pipeline and operator scripts; Postgres mirror (when API `backend=postgres`) is for faster list reads, not send approval.
- **No raw email bodies** or filesystem paths in the UI (subject/snippet previews only).

### Smoke (API)

```bash
curl -sS http://127.0.0.1:8001/health
curl -sS 'http://127.0.0.1:8001/operator/status?max_staleness_days=14'
curl -sS 'http://127.0.0.1:8001/cases/warm?limit=10&positive_signal_only=false'
curl -sS 'http://127.0.0.1:8001/opportunities/equipment?limit=10'
```

## Tests and build

```bash
cd apps/dashboard
npm test
npm run build
```

Policy tests assert dashboard `src/` has no mutating `fetch` methods and no direct DB/pipeline imports.

---

## Legacy panel (email-pipeline FastAPI on :8000)

The sections below describe the older multi-tab panel that called email-pipeline routes (`/dashboard/summary`, `/classification/*`, …). That stack is separate from Dashboard v0.

Documentación operador: [`../email-pipeline/docs/RUNBOOK.md#m-eprun-dashboard-gmail-to-react`](../email-pipeline/docs/RUNBOOK.md#m-eprun-dashboard-gmail-to-react)

### Arranque rápido (legacy)

**Terminal 1 — API** (desde `apps/email-pipeline`):

```bash
uv sync --group gmail --group postgres --group api
export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"

uv run alembic -c alembic.ini upgrade head
uv run python scripts/sync/sync_dashboard_postgres_mirror.py

uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8000 --reload
```

Point `VITE_ORIGENLAB_API_BASE_URL=http://127.0.0.1:8000` if you run the legacy tabs against that server.

### Pruebas (legacy smoke)

```bash
npm run smoke   # requiere API levantada en el puerto configurado
```
