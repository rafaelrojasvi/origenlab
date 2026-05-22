# API-3 Phase 1 — Mirror route relocation design

**Status:** Phase **1A–1G complete**; Phase **2 parity checklist frozen** — see [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md). Design reference for Phases 3–6.  
**Prerequisite:** [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md)  
**Scope:** All legacy Postgres mirror GET routes (except `/health`) relocated under `/mirror/*`. Operator `GET /contacts/{email}` unchanged. Legacy `:8000` tree retained until Phase 6.

This document defines how to relocate the legacy Postgres mirror API (`apps/email-pipeline/src/origenlab_api`, port **8000**) into **`apps/api` (port 8001)** under a dedicated **`/mirror`** namespace, while keeping the legacy tree alive through cutover.

---

## Design goals

| Goal | Constraint |
|------|------------|
| Single operator port | Prefer **:8001 only** for new consumers (Streamlit, RUNBOOK, smokes) after cutover |
| No Today regression | **Do not** change `GET /health`, `/operator/status`, `/cases/warm`, `/opportunities/equipment`, `/contacts/{email}`, `/emails/recent` |
| No contact collision | Mirror **list** at `/mirror/contacts`; operator **detail** stays at `/contacts/{email}` |
| Read-only | Mirror routes remain **GET only**; no Gmail/SQLite/CSV mutations from HTTP |
| Parity first | Legacy `:8000` stays until Phase 4+ deprecation window and Phase 5 grep audit pass |
| **Do not delete** | `apps/email-pipeline/src/origenlab_api` remains until Phase 6 criteria met |

---

## Target namespace: `/mirror`

All relocated routes live under prefix **`/mirror`**, tagged in OpenAPI as **`postgres-mirror`** (or `mirror-v1`). This keeps them visually and mechanically separate from the SQLite-first **operator plane**.

### Route map (legacy :8000 → future :8001)

| Legacy route (port 8000) | Phase 1 route (port 8001) | Query params (unchanged semantics) | Response model source |
|--------------------------|---------------------------|-------------------------------------|------------------------|
| `GET /health` | *(no mirror alias)* | — | Use existing operator `GET /health` on `apps/api` (different JSON contract) |
| `GET /health/dependencies` | `GET /mirror/health/dependencies` | — | Legacy `HealthDependenciesResponse` (Postgres + SQLite ping) |
| `GET /meta/dashboard-sync` | `GET /mirror/meta/dashboard-sync` | — | `DashboardSyncMetaResponse` |
| `GET /dashboard/summary` | `GET /mirror/dashboard/summary` | `scope=canonical` \| `archive` | `DashboardSummaryResponse` |
| `GET /classification/summary` | `GET /mirror/classification/summary` | — | `ClassificationSummaryResponse` |
| `GET /classification/recent` | `GET /mirror/classification/recent` | `label`, `limit` | `ClassificationRecentResponse` |
| `GET /classification/actions` | `GET /mirror/classification/actions` | — | `ClassificationActionsResponse` |
| `GET /commercial/purchase-events` | `GET /mirror/commercial/purchase-events` | `limit`, filters TBD from legacy | `CommercialPurchaseEventsListResponse` |
| `GET /commercial/purchase-events/{event_id}` | `GET /mirror/commercial/purchase-events/{event_id}` | path `event_id` | `CommercialPurchaseEventDetailResponse` |
| `GET /contacts` | `GET /mirror/contacts` | `limit`, `offset`, `domain`, `q`, `scope` | `PaginatedContactsResponse` |
| `GET /organizations` | `GET /mirror/organizations` | `limit`, `offset`, … | `PaginatedOrganizationsResponse` |
| `GET /outbound/suppressions/emails` | `GET /mirror/outbound/suppressions/emails` | pagination | `PaginatedEmailSuppressionsResponse` |
| `GET /outbound/contact-state` | `GET /mirror/outbound/contact-state` | pagination | `PaginatedOutreachStateResponse` |
| `GET /outbound/readiness` | `GET /mirror/outbound/readiness` | — | `OutboundReadinessResponse` |

**Not relocated to root paths** — e.g. no `GET /dashboard/summary` on `:8001` (would confuse operator smoke policies and parked legacy client expectations).

### FastAPI mount order (apps/api)

```text
create_app()
  include_router(health.router)           # GET /health
  include_router(operator.router)         # GET /operator/status
  include_router(emails.router)           # GET /emails/recent
  include_router(cases.router)            # GET /cases/warm
  include_router(opportunities.router)    # GET /opportunities/equipment
  include_router(mirror.router)           # GET /mirror/...   ← new tree
  include_router(contacts.router)         # GET /contacts/{email}  ← after mirror
```

`/mirror/contacts` cannot be captured by `/contacts/{email}` because the mirror path has an extra segment. Still register **mirror before** contacts for clarity and future-proofing.

---

## Proposed `apps/api` package layout (implementation phases ≥2)

Planning target only — no files created in Phase 1 design:

```text
apps/api/src/origenlab_api/
  mirror/
    __init__.py
    routers/
      health.py          # /mirror/health/dependencies
      meta.py
      dashboard.py
      classification.py
      commercial.py
      contacts.py          # list only
      organizations.py
      outbound.py
    schemas/             # Pydantic models (copy or re-export from shared module)
    services/            # thin handlers → repository
    repositories/
      postgres_mirror.py # calls shared query functions
  routes/                # unchanged operator plane
  ...
```

OpenAPI: second tag group **Mirror (Postgres)** so operators see operator vs mirror sections in `/docs`.

---

## Shared repository / query code reuse

### Current legacy implementation

| Module | Role |
|--------|------|
| `email-pipeline/.../origenlab_api/services/queries.py` | **~900 lines** — all Postgres mart/outbound/commercial SQL |
| `email-pipeline/.../origenlab_api/db.py` | `postgres_connection`, `table_exists`, `fetch_one` / `fetch_all` |
| `email-pipeline/.../origenlab_api/schemas.py` | Pydantic response models for mirror API |
| `email-pipeline/.../origenlab_api/deps.py` | `get_postgres_url`, settings dict |
| `email-pipeline/.../origenlab_api/routers/*.py` | Thin FastAPI wiring |

### Already in `apps/api` (operator Postgres backend)

| Module | Overlap with mirror |
|--------|---------------------|
| `repositories/postgres/common.py` | `postgres_connection(settings)` — **similar** to legacy `db.py` but settings-driven |
| `repositories/postgres/operator.py` | Operator verdict only — **not** dashboard summary |
| `repositories/postgres/warm_cases.py` | `api.v_warm_case` — **not** mart rollups |
| `repositories/postgres/contact.py` | **Detail** by email — different from mart contact **list** |

**Conclusion:** Mirror relocation is mostly **new surface area** over **mart/reporting/commercial** schemas, not reuse of existing `apps/api` operator repos.

### Recommended shared-module strategy (minimize drift)

**Phase 1 implementation (future PRs):**

1. **Extract** query functions + Pydantic schemas from `email-pipeline/.../origenlab_api` into a **neutral** import path under email-pipeline, e.g.  
   `origenlab_email_pipeline/postgres_dashboard_api/`  
   (`queries.py`, `schemas.py`, `db_helpers.py`) — **not** named `origenlab_api`.

2. **Legacy routers** (port 8000) become thin wrappers importing the neutral module (optional but strongly recommended during transition).

3. **`apps/api` mirror layer** imports the same neutral module; uses `apps/api` `Settings.require_postgres_url()` and existing `repositories/postgres/common.py` for connections where possible.

4. **Unify** duplicate `postgres_connection` helpers over time — one connection factory in `apps/api`, mirror repos call it.

**Do not** add `email-pipeline/src/origenlab_api` to `apps/api` `sys.path` at runtime (package name collision). **Do** depend on `origenlab-email-pipeline` package for shared SQL + types.

### Postgres dependency

| Requirement | Notes |
|-------------|--------|
| `ORIGENLAB_API_BACKEND=postgres` | Mirror routes return **503** or structured empty + `reduced_mode` when URL missing — match legacy behavior |
| `uv sync --group postgres` | Required for mirror route tests in `apps/api` |
| Disposable DB only in CI | Reuse `origenlab_dashboard2_test` on `127.0.0.1:5433` pattern from matrix docs |
| Statement timeout | Reuse `Settings.postgres_statement_timeout_ms` from `apps/api` |

Mirror routes **must not** require SQLite for data (except optional ping in `/mirror/health/dependencies` mirroring legacy).

---

## Tests to relocate (email-pipeline → apps/api)

| Current file | Future home | Primary routes asserted |
|--------------|-------------|-------------------------|
| `tests/test_api_slice1.py` | `apps/api/tests/mirror/test_dashboard_summary.py` (+ contacts/orgs/outbound slices) | `/mirror/dashboard/summary`, scope canonical/archive |
| `tests/test_api_classification.py` | `apps/api/tests/mirror/test_classification.py` | `/mirror/classification/*` |
| `tests/test_api_meta.py` | `apps/api/tests/mirror/test_meta_sync.py` | `/mirror/meta/dashboard-sync` |
| `tests/test_api_commercial_purchase_events.py` | `apps/api/tests/mirror/test_mirror_commercial_purchase.py` | `/mirror/commercial/purchase-events` |
| `tests/test_api_slice1.py` | `apps/api/tests/mirror/test_mirror_mart_lists.py` | `/mirror/contacts`, `/mirror/organizations` |
| `tests/test_api_cors.py` | Split: `apps/api/tests/mirror/test_mirror_cors.py` + keep operator CORS policy elsewhere | `Access-Control-Allow-Origin` for Vite origins |
| `tests/test_streamlit_api_preview.py` | Stay in **email-pipeline** until Phase 3; update paths only | URL builder for `/mirror/...` |
| `tests/test_business_mart_app_ux.py` | Stay in email-pipeline | Sidebar gate on env |
| `tests/test_doc_dashboard_runbook.py` | Stay in email-pipeline until Phase 3 | Assert RUNBOOK curl strings |

**New tests in `apps/api` (Phase 2):**

- `test_mirror_import_guard.py` — mirror routers load from `apps/api/src` only
- `test_mirror_no_write_policy.py` — GET-only mirror tree
- `test_mirror_parity.py` — optional dual-host test: same fixture against `:8000` and `:8001` during deprecation window (httpx, skipped if legacy not running)
- Extend `test_no_write_policy.py` — forbid `/mirror` handlers from registering POST/PUT/PATCH/DELETE

**Keep running legacy tests** until Phase 4; then delete or mark `pytest.mark.legacy_api` skipped.

---

## Docs and Streamlit references (change in Phase 3+)

| Artifact | Current legacy reference | Target after cutover |
|----------|-------------------------|----------------------|
| `streamlit_api_preview.py` | `DEFAULT_API_BASE_URL = http://127.0.0.1:8000`; `/health`, `/dashboard/summary`, `/outbound/readiness` | `http://127.0.0.1:8001`; `/mirror/dashboard/summary`, `/mirror/outbound/readiness`; operator `/health` optional |
| `RUNBOOK.md` | All `:8000` curls | `:8001` + `/mirror/...` |
| `dashboard_postgres_sync.py` | Post-sync curl hints `:8000/dashboard/summary` | `:8001/mirror/dashboard/summary` |
| `.env.example` (email-pipeline) | `ORIGENLAB_API_BASE_URL=http://127.0.0.1:8000` | Comment default `http://127.0.0.1:8001` |
| `EXPERIMENTAL_PARKED.md` | Port 8000 narrative | Dual-port deprecation note |
| `POSTGRES_API_DASHBOARD_PLAN.md` | Historical | Link to this design |
| `apps/api/README.md` | API-3 audit link | Phase 1 design + mirror route table |
| `apps/dashboard/scripts/legacy-smoke.mjs` | `:8000` `/dashboard/summary` | Repoint or retire in Phase 4 |
| `apps/dashboard/src/legacy/api/client.ts` | Full legacy path set | **Parked** — repoint only if product revives multi-tab UI; otherwise archive |

**Frozen Today dashboard** (`operatorClient.ts`, `smoke-v1.mjs`) — **no changes** in API-3 mirror work.

---

## Phased migration plan

### Phase 1 — Add mirror routes on `apps/api` (legacy :8000 stays alive)

**Deliverables:**

- New `/mirror/*` routers on `:8001` with **response parity** to legacy OpenAPI models.
- Mirror enabled only when `ORIGENLAB_API_BACKEND=postgres` and `ORIGENLAB_POSTGRES_URL` set (or explicit `mirror` feature flag env — TBD in implementation).
- Shared query module extraction started (neutral `origenlab_email_pipeline` path).
- Documentation: this design doc + update audit checklist.
- **No** removal of `email-pipeline/src/origenlab_api`.
- **No** changes to active operator routes or Dashboard Today.

**Exit criteria:** Manual `curl` parity for key routes on disposable Postgres; `apps/api` mirror tests green with `--group postgres`.

### Phase 2 — Parity tests

**Deliverables:**

- Port `test_api_*` coverage to `apps/api/tests/mirror/`.
- Optional side-by-side parity script: compare JSON shape (not necessarily byte-identical timestamps) `:8000` vs `:8001/mirror/*`.
- CI job: postgres group tests for mirror only (disposable URL).

**Exit criteria:** CI mirror suite ≥ legacy route coverage; no undocumented route gaps in route map table above.

### Phase 3 — Repoint consumers

**Deliverables:**

- Streamlit API preview paths → `:8001` `/mirror/...`.
- RUNBOOK + `dashboard_postgres_sync` hints updated.
- `test_doc_dashboard_runbook.py` expected strings updated.
- Optional: `legacy-smoke.mjs` → `mirror-smoke.mjs` on `:8001`.

**Exit criteria:** Operator workflow on disposable Postgres uses **only** `:8001` in docs; `:8000` marked deprecated in RUNBOOK.

### Phase 4 — Deprecation window

**Deliverables:**

- Legacy `:8000` uvicorn documented as **deprecated** (still runs).
- Log warning on legacy app startup: “use apps/api /mirror routes”.
- Minimum **4 weeks** (or one release cycle) with no internal reliance on `:8000` — duration TBD with operator.

**Exit criteria:** Grep shows no production/internal scripts defaulting to `:8000` except legacy package itself.

### Phase 5 — Second grep audit

Run audit commands from [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md) plus:

```bash
rg '/mirror/' apps/api/src/origenlab_api/routes   # ensure operator routes unchanged
rg 'test_api_' apps/email-pipeline/tests          # should be empty or skipped
rg 'origenlab_api\.routers' apps/email-pipeline/src/origenlab_api  # pre-delete baseline
```

**Exit criteria:** Signed checklist — zero runtime references to legacy paths on `:8000`.

### Phase 6 — Delete legacy tree (only if zero references)

**Preconditions (all required):**

- Phases 1–5 complete.
- `apps/email-pipeline/src/origenlab_api` has **no** imports from rest of pipeline except tests/docs (grep).
- Parked `apps/dashboard/src/legacy/` disposition decided (delete or keep as archive **without** `:8000` default).
- Product sign-off on removing port **8000** from RUNBOOK.

**Explicit recommendation:** **Do not delete** until every precondition is checked. If any consumer remains, **extend deprecation** instead.

---

## Risks and mitigations

### 1. Package name collision (`origenlab_api`)

| Risk | Importing legacy `origenlab_api` from `apps/api` process loads wrong `main.py`. |
| Mitigation | Shared logic lives under `origenlab_email_pipeline.*`; `test_import_guard.py` unchanged; mirror code only under `apps/api/src/origenlab_api/mirror/`. |

### 2. Route collision (`/contacts` list vs `/contacts/{email}` detail)

| Risk | FastAPI could mis-route if paths poorly ordered. |
| Mitigation | Mirror list **only** at `/mirror/contacts`; register mirror router **before** contacts detail; add regression test `GET /mirror/contacts` and `GET /contacts/foo@bar.cl` both resolve correctly. |

### 3. Postgres dependency and env drift

| Risk | Mirror routes hit wrong DB (scratch/prod) if env not cleared. |
| Mitigation | Reuse freeze checklist env unset for default CI; mirror tests require `ORIGENLAB_TEST_POSTGRES_URL`; settings validation in `validate_api_settings`. |

### 4. CORS / Vite proxy

| Risk | Dashboard dev proxy only forwards operator paths today (`/health`, `/operator`, `/cases`, `/opportunities`, `/contacts`). |
| Mitigation | Phase 3 optional: add `/mirror` to `vite.config.ts` proxy **only if** a future UI consumes mirror (Today does not). Streamlit uses direct URL, not Vite. Document CORS `ORIGENLAB_API_CORS_ORIGINS` on `apps/api` if browser clients appear. |

### 5. Response shape drift

| Risk | Operator `GET /health` vs legacy `GET /health` differ; clients conflate them. |
| Mitigation | No alias; document in RUNBOOK; mirror health only at `/mirror/health/dependencies`. |

### 6. Parked dashboard legacy React (`apps/dashboard/src/legacy/`)

| Risk | Reviving multi-tab UI without path update hits wrong host. |
| Mitigation | Leave parked; if revived, point `legacy/api/client.ts` at `/mirror/*` on `:8001` in Phase 3 or keep archive-only. **Active Today unchanged.** |

### 7. Dual maintenance during Phases 1–4

| Risk | Bug fixes applied only to one copy of SQL. |
| Mitigation | Shared `origenlab_email_pipeline/postgres_dashboard_api` module; legacy routers thin; parity test in Phase 2. |

### 8. `eventually_consistent` / scope semantics

| Risk | Operators treat mirror `READY` as send approval. |
| Mitigation | Preserve `POSTGRES_MIRROR_NOTE` / Spanish notes in responses; banner text unchanged on Today. |

---

## Explicit no-delete recommendation

**Do not delete** `apps/email-pipeline/src/origenlab_api` during Phase 1 or Phase 2.

Deletion is **Phase 6 only**, contingent on Phase 5 grep audit and product sign-off. Until then:

- Keep legacy uvicorn instructions in RUNBOOK (marked deprecated after Phase 4).
- Keep `test_api_*` in email-pipeline until cutover tests prove mirror parity.
- Keep parked dashboard legacy client in repo unless explicitly removed.

---

## Phase 1A–1G implemented (partial)

| Item | Status |
|------|--------|
| `/mirror` router scaffold | **Done** (`origenlab_api/mirror/`) |
| `GET /mirror/health/dependencies` | **Done** (1A) |
| `GET /mirror/meta/dashboard-sync` | **Done** (1A) |
| `GET /mirror/dashboard/summary` | **Done** (1B; `scope=canonical\|archive`) |
| `GET /mirror/outbound/readiness` | **Done** (1C) |
| `GET /mirror/outbound/suppressions/emails` | **Done** (1D) |
| `GET /mirror/outbound/contact-state` | **Done** (1D) |
| `GET /mirror/classification/summary` | **Done** (1E) |
| `GET /mirror/classification/recent` | **Done** (1E; `label`, `limit`) |
| `GET /mirror/classification/actions` | **Done** (1E) |
| `GET /mirror/commercial/purchase-events` | **Done** (1F; `limit` 1–100) |
| `GET /mirror/commercial/purchase-events/{event_id}` | **Done** (1F) |
| `GET /mirror/contacts` | **Done** (1G; `limit`, `offset`, `domain`, `q`, `scope`) |
| `GET /mirror/organizations` | **Done** (1G; same params) |
| Shared module | **Done** (`postgres_dashboard_api/mart_lists.py`, …) |
| Operator `GET /health`, `/operator/status`, `/contacts/{email}` | **Unchanged** |
| Legacy `:8000` deleted | **No** |
| Write endpoints | **None** |

Tests: `apps/api/tests/mirror/` (GET-only policy, import guard, mocked parity, Phase 2 parity matrix). Optional integration when `ORIGENLAB_TEST_POSTGRES_URL` is set. Optional dual-server smoke: `scripts/mirror_parity_smoke.py`.

---

## Phase 2 parity freeze

| Item | Status |
|------|--------|
| Parity matrix doc | **Done** — [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) |
| OpenAPI / policy tests | **Done** — `test_mirror_phase2_parity.py` |
| Legacy `/health` unmirrored | **Documented** |
| Streamlit / RUNBOOK cutover | **Phase 3A** — docs/smokes prefer :8001 `/mirror/*`; legacy :8000 deprecated |
| Legacy tree deleted | **No** |

---

## Related documents

| Document | Role |
|----------|------|
| [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) | Phase 2 sign-off matrix + optional live smoke |
| [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md) | Reference inventory + consumers |
| [../README.md](../README.md) | Active operator API |
| [../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md](../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md) | Today dashboard freeze (unchanged by API-3) |
| [../../email-pipeline/docs/RUNBOOK.md](../../email-pipeline/docs/RUNBOOK.md) | Legacy runbook (Phase 3 updates) |
