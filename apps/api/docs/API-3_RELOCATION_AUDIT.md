# API-3 — Legacy `origenlab_api` relocation audit

**Status:** Audit + Phase 2 parity freeze (2026-05).  
**Scope:** Phase 1 mirror relocation complete on `:8001`; parity matrix frozen in [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md). No legacy tree deletion; no Streamlit/RUNBOOK cutover yet.

This document records every known reference to the legacy FastAPI app in `apps/email-pipeline/src/origenlab_api` (conventionally served on port **8000**). Use it before any API-3 implementation that relocates mirror routes into `apps/api`.

---

## Two `origenlab_api` packages

The repository contains **two separate Python packages** with the same import name `origenlab_api`. Only one should be on `sys.path` per process.

| Location | Port (convention) | Role |
|----------|-------------------|------|
| **`apps/api/src/origenlab_api`** | **8001** | **Active dashboard / operator API.** SQLite-first (optional Postgres mirror). Powers Dashboard v1/v2 Today (`GET /health`, `/operator/status`, `/cases/warm`, `/opportunities/equipment`, `/contacts/{email}`, `/emails/recent`). |
| **`apps/email-pipeline/src/origenlab_api`** | **8000** | **Legacy Postgres mirror / multi-tab API** (Slice 1). Read-only routes over mart/outbound mirrors (`/dashboard/*`, `/classification/*`, `/commercial/*`, …). |

**Run the active API from `apps/api`:**

```bash
cd apps/api
uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8001 --reload
```

**Run the legacy API from `apps/email-pipeline`:**

```bash
cd apps/email-pipeline
uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8000 --reload
```

`apps/api/tests/test_import_guard.py` asserts `origenlab_api.main` loads from **`apps/api/src`** when pytest runs in `apps/api`.

### Route surface comparison

**Legacy (:8000) — all GET, Postgres mirror:**

| Prefix | Routes |
|--------|--------|
| *(root)* | `GET /health`, `GET /health/dependencies` |
| `/meta` | `GET /meta/dashboard-sync` |
| `/dashboard` | `GET /dashboard/summary` (`scope=canonical` \| `archive`) |
| `/classification` | `GET /classification/summary`, `/recent`, `/actions` |
| `/commercial` | `GET /commercial/purchase-events`, `/commercial/purchase-events/{id}` |
| `/contacts` | `GET /contacts` (paginated **list**, mart scope) |
| `/organizations` | `GET /organizations` |
| `/outbound` | `GET /outbound/suppressions/emails`, `/contact-state`, `/readiness` |

**Active (:8001) — operator plane + mirror (Phase 1 complete):**

| Route | Notes |
|-------|--------|
| `GET /health` | Operator contract (not legacy `/health`) |
| `GET /operator/status` | Verdict + warnings |
| `GET /cases/warm` | Warm commercial queue |
| `GET /opportunities/equipment` | Equipment-first CSV manifest queue |
| `GET /contacts/{email}` | **Detail** by email (not the legacy list) |
| `GET /emails/recent` | Recent email previews |
| `GET /mirror/*` | **13 legacy read-route twins** — see [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) |

**Important:** `GET /contacts` (legacy list) → `GET /mirror/contacts`; `GET /contacts/{email}` (operator detail) stays separate.

---

## Do not delete the legacy API yet

**Explicit policy:** Do **not** delete `apps/email-pipeline/src/origenlab_api` or stop documenting port **8000** until the safe migration plan below is complete and a follow-up grep audit shows no remaining runtime or CI dependencies.

**Zero references are not proven.** This audit found:

- Runtime consumers (Streamlit optional page)
- Operator documentation and post-sync hints
- email-pipeline pytest modules (`test_api_*.py`)
- Parked dashboard client code (`apps/dashboard/src/legacy/`)
- Manual smoke script (`legacy-smoke.mjs`)

**Dashboard v1 Today is already decoupled** — it uses `apps/api` on :8001 only. API-3 relocation targets the **Postgres mirror / experimental stack**, not the frozen Today page.

---

## Current legacy users

### Runtime / operator tooling

| Consumer | Location | Legacy usage |
|----------|----------|--------------|
| **Streamlit API preview** | `apps/email-pipeline/src/origenlab_email_pipeline/streamlit_api_preview.py` → `apps/business_mart_app.py` | When `ORIGENLAB_API_BASE_URL` is set (default `http://127.0.0.1:8000`): `GET /health`, `/dashboard/summary?scope=canonical`, `/outbound/readiness` |
| **RUNBOOK curls** | `apps/email-pipeline/docs/RUNBOOK.md` | Postgres mirror validation: `/health`, `/dashboard/summary`, `/meta/dashboard-sync`, `/classification/summary`, `/commercial/purchase-events`, archive scope |
| **`dashboard_postgres_sync.py` hints** | `apps/email-pipeline/src/origenlab_email_pipeline/dashboard_postgres_sync.py` | Post-sync operator messages with `curl` to `:8000/dashboard/summary` |

### Dashboard (parked / manual)

| Consumer | Location | Legacy usage |
|----------|----------|--------------|
| **Parked React legacy** | `apps/dashboard/src/legacy/` | `legacy/api/client.ts` calls `/dashboard/summary`, `/outbound/readiness`, `/contacts`, `/organizations`, `/meta/dashboard-sync`, `/classification/*`, `/commercial/purchase-events`. **Not mounted** in `App.tsx`; excluded from `npm test` |
| **`legacy-smoke.mjs`** | `apps/dashboard/scripts/legacy-smoke.mjs` | Manual `npm run smoke:legacy`: `/health`, `/dashboard/summary`. **Not** part of v1 freeze CI |

### Tests (email-pipeline CI)

| Module | Coverage |
|--------|----------|
| `tests/test_api_slice1.py` | `/dashboard/summary`, contacts, organizations, outbound, scope |
| `tests/test_api_classification.py` | `/classification/*` |
| `tests/test_api_meta.py` | `/meta/dashboard-sync` |
| `tests/test_api_commercial_purchase_events.py` | `/commercial/purchase-events` |
| `tests/test_api_cors.py` | CORS + `/dashboard/summary` |
| `tests/test_streamlit_api_preview.py` | URL helpers, `fetch_json`, env |
| `tests/test_business_mart_app_ux.py` | Sidebar “API preview” when env set |
| `tests/test_doc_dashboard_runbook.py` | RUNBOOK curl strings + dashboard README markers |

### Active dashboard — does **not** use legacy

- `apps/dashboard/src/api/operatorClient.ts` → `:8001` / Vite proxy
- `scripts/smoke-v1.mjs`, `apps/api/scripts/dashboard_v1_http_smoke.py` forbid `/dashboard/`, `/classification/`, `/commercial/`
- Policy tests: `dashboard0Safety.test.ts`, `noWritePolicy.test.ts`, `smokeV1Policy.test.ts`
- `devApiConfig.ts` warns if `VITE_ORIGENLAB_API_BASE_URL` points at `:8000`

### Documentation references (policy / guardrails)

- `apps/api/README.md` — package collision + API-3 roadmap pointer
- `apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`, `BACKEND_MATRIX_VALIDATION.md`, `README.md`
- `apps/email-pipeline/docs/EXPERIMENTAL_PARKED.md`, `POSTGRES_API_DASHBOARD_PLAN.md`
- `apps/dashboard/.env.example` — do not point dev at `:8000`

### False positives (not this API)

- Unrelated `--port 8000` in `scripts/leads/advanced/run_contact_hunt_web_server.py`
- String limits / SVG paths containing `8000` as a number, not a URL

---

## Safe migration plan

Execute in order. Do not skip the grep audit or delete the legacy tree early.

### 1. Recreate needed legacy routes under `apps/api` `/mirror/*`

**Phase 1 design (detailed route map, phases, risks):** [API-3_PHASE1_MIRROR_ROUTE_DESIGN.md](./API-3_PHASE1_MIRROR_ROUTE_DESIGN.md).

Add read-only routes on **`apps/api` (:8001)** that preserve legacy response shapes, for example:

```
GET /mirror/health/dependencies
GET /mirror/meta/dashboard-sync
GET /mirror/dashboard/summary
GET /mirror/classification/summary
GET /mirror/classification/recent
GET /mirror/classification/actions
GET /mirror/commercial/purchase-events
GET /mirror/commercial/purchase-events/{id}
GET /mirror/contacts
GET /mirror/organizations
GET /mirror/outbound/suppressions/emails
GET /mirror/outbound/contact-state
GET /mirror/outbound/readiness
```

Implement by **moving or sharing** query logic from `email-pipeline/src/origenlab_api/services/queries.py` (or thin wrappers), not by breaking existing operator routes (`/cases/warm`, `/contacts/{email}`, etc.).

### 2. Move Streamlit and docs to :8001 mirror routes

- Update `streamlit_api_preview.py` default base URL and paths to `:8001` + `/mirror/...`.
- Update `apps/email-pipeline/docs/RUNBOOK.md` curl examples.
- Update `dashboard_postgres_sync.py` post-sync hints.
- Keep `ORIGENLAB_API_BASE_URL` env name; document new default `http://127.0.0.1:8001`.

### 3. Port tests

- Relocate or duplicate `test_api_*.py` coverage against `apps/api` mirror routes.
- Keep legacy tests green until cutover, then remove duplicate phase.

### 4. Retire `legacy-smoke` or repoint it

- Either delete `apps/dashboard/scripts/legacy-smoke.mjs` and `smoke:legacy` npm script, or point at `:8001` `/mirror/dashboard/summary`.
- v1 freeze CI continues to use `smoke-v1.mjs` only.

### 5. Run grep audit

Before any delete, confirm no remaining references:

```bash
rg '127\.0\.0\.1:8000|localhost:8000' --glob '*.{py,ts,tsx,mjs,sh,md}'
rg '/dashboard/summary|/classification/|/commercial/purchase' apps/dashboard/src --glob '!legacy/**'
rg 'from origenlab_api.main import' apps/email-pipeline
```

Expect parked `apps/dashboard/src/legacy/` until product explicitly drops the archive.

### 6. Only then delete the legacy tree

Delete `apps/email-pipeline/src/origenlab_api` **only when**:

- Streamlit + RUNBOOK + sync hints use :8001 mirror routes
- email-pipeline `test_api_*` modules pass against `apps/api`
- Optional: parked dashboard `src/legacy/` removed or archived outside repo
- Grep audit shows no operator/runtime dependency on :8000 legacy paths

Until step 6, **keep** the legacy package and port **8000** documented in RUNBOOK.

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) | Phase 2 route matrix + smoke |
| [../README.md](../README.md) | Active API run + import guard |
| [../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md](../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md) | Dashboard v1/v2 freeze; legacy :8000 warning |
| [../../dashboard/src/legacy/README.md](../../dashboard/src/legacy/README.md) | Parked multi-tab React client |
| [../../email-pipeline/docs/RUNBOOK.md](../../email-pipeline/docs/RUNBOOK.md) | Legacy uvicorn + curl validation |

---

## Phase 2 parity sign-off

| Item | Result |
|------|--------|
| All legacy read routes mirrored (except `/health`) | **Yes** — 13 pairs in parity checklist |
| Parity tests + optional `mirror_parity_smoke.py` | **Yes** |
| Legacy tree deleted | **No** |
| Streamlit / RUNBOOK repointed to :8001 mirror | **Phase 3A** — docs/smokes prefer `/mirror/*`; :8000 kept deprecated |
| Dashboard Today routes changed | **No** |
| Write actions | **None** |

---

## Phase 3A consumer cutover (partial)

Low-risk consumers now document or default to **`apps/api` :8001** `/mirror/*`:

| Consumer | Status |
|----------|--------|
| `apps/email-pipeline/docs/RUNBOOK.md` | Mirror curls first; legacy :8000 deprecated block retained |
| `dashboard_postgres_sync.py` post-sync hints | `:8001/mirror/...` before `:8000/...` |
| `streamlit_api_preview.py` | Default `http://127.0.0.1:8001`; auto `/mirror/*` unless base ends with `:8000` |
| `apps/dashboard/scripts/mirror-smoke.mjs` + `npm run smoke:mirror` | GET smoke for key mirror routes |
| `npm run smoke:legacy` | **Kept** — parked :8000 smoke |
| Dashboard Today (`operatorClient`, Vite proxy) | **Unchanged** |
| Parked `src/legacy/` React client | **Unchanged** (still :8000 paths if revived) |

---

## Audit checklist sign-off (original)

| Item | Result |
|------|--------|
| Legacy tree deleted | **No** — policy: do not delete yet |
| Phase 1 mirror routes on `apps/api` | **Yes** — under `/mirror/*` |
| Dashboard features added | **No** |
| Write actions | **None** |
