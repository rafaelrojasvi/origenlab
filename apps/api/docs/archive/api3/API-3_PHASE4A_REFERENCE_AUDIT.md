# API-3 Phase 4A — Post-deprecation reference audit

**Date:** 2026-05 (grep audit after Phase 3C deprecation headers)  
**Method:** Repository search for `:8000`, legacy route families, `origenlab_api` tree, `smoke:legacy`, and `src/legacy`.  
**Enforcement:** `apps/api/tests/mirror/test_mirror_phase4a_reference_audit.py`

---

## Executive summary

| Metric | Result |
|--------|--------|
| Zero `:8000` references | **Not proven** — intentional deprecated + test + parked refs remain |
| Safe to delete `apps/email-pipeline/src/origenlab_api` | **No** — Phase 6 gate not met |
| Dashboard Today uses `:8000` or `/mirror/*` | **No** — operator `:8001` only |
| Preferred mirror reporting | **`:8001` `/mirror/*`** (documented in RUNBOOK, sync hints, Streamlit default) |

**Explicit no-delete:** Keep legacy tree and `:8000` routes until Phase 6 grep shows **no runtime dependency** outside categories 2–4 below.

---

## Classification legend

| Code | Meaning |
|------|---------|
| **1** | Already repointed to `:8001` `/mirror/*` (or shared `postgres_dashboard_api`) |
| **2** | Intentional deprecated compatibility (must stay until Phase 6) |
| **3** | Parked / legacy UI (not mounted in Dashboard v1) |
| **4** | Test / smoke validating legacy compatibility or anti-patterns |
| **5** | Should be repointed or updated in **Phase 4B** |
| **6** | False positive / historical doc / guardrail only |

---

## Counts by category (significant references)

| Category | Approx. count | Notes |
|----------|---------------|--------|
| **1** Repointed | **28** | RUNBOOK mirror curls, sync hints, Streamlit `:8001` + `/mirror/*`, `smoke:mirror`, apps/api mirror routers, shared module |
| **2** Deprecated compatibility | **22** | Legacy uvicorn, `:8000` curl blocks, `legacy-smoke.mjs`, dual-server parity legacy host, deprecation middleware |
| **3** Parked legacy UI | **12 files** | `apps/dashboard/src/legacy/**` (client + tabs); excluded from `npm test` |
| **4** Legacy tests / policy | **14** | `test_api_*`, deprecation headers, runbook doc markers, Streamlit `:8000` path tests |
| **5** Phase 4B action | **6** | Stale audit rows, architecture plan deployment port, optional Streamlit test refresh |
| **6** False positive / guard | **11** | `devApiConfig` warnings, `dashboard0Safety` forbidden fragments, operator `/contacts/{email}`, vite proxy |

**Total classified hits (non-duplicate groups):** **93**  
**Runtime dependencies on legacy `:8000` for production Dashboard:** **0**

---

## `:8000` / `localhost:8000` inventory

| Location | Category | Safe / action |
|----------|----------|---------------|
| `apps/email-pipeline/docs/RUNBOOK.md` — legacy uvicorn + deprecated curl block | **2** | Intentional; keep until Phase 6 |
| `apps/email-pipeline/docs/RUNBOOK.md` — mirror curls `:8001` | **1** | Preferred operator path |
| `apps/email-pipeline/src/origenlab_api/` — served on `:8000` | **2** | Implementation of deprecated API |
| `apps/email-pipeline/src/origenlab_api/deprecation.py` | **2** | Deprecation signal |
| `apps/email-pipeline/.../dashboard_postgres_sync.py` — legacy curl hint line | **2** | After `:8001` mirror hints |
| `apps/email-pipeline/.env.example` — commented `# ...8000` | **2** | Legacy override documented |
| `apps/email-pipeline/tests/test_*` — legacy URL fixtures | **4** | Compatibility tests |
| `apps/api/scripts/mirror_parity_smoke.py` — `--legacy-base` default | **2** | Dual-server parity |
| `apps/api/scripts/run_mirror_dual_server_parity.sh` | **2** | Live parity orchestration |
| `apps/dashboard/scripts/legacy-smoke.mjs` — default base | **2** | `smoke:legacy`; keep |
| `apps/dashboard/scripts/mirror-smoke.mjs` — comment only | **1** | Points to `smoke:mirror` |
| `apps/dashboard/src/legacy/api/client.ts` — `DEFAULT_BASE` | **3** | Parked client |
| `apps/dashboard/src/lib/devApiConfig.ts` + tests | **6** | Warns **against** `:8000` |
| `apps/dashboard/src/pages/TodayPage.test.tsx` | **6** | Asserts warning when env set to `:8000` |
| `apps/dashboard/README.md` — wrong dev env table | **6** | Documents anti-pattern |
| `apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md` | **6** | Warns unset `:8000` env |
| `apps/api/docs/*` (API-3 series) | **1/2** | Migration + deprecation narrative |
| `apps/api/README.md` | **1/2** | Coexistence + parity commands |

---

## Legacy route family inventory

### `/dashboard/summary`

| Location | Cat | Notes |
|----------|-----|-------|
| `postgres_dashboard_api/summary.py` + mirror route | **1** | Shared logic |
| `origenlab_api/routers/dashboard.py` | **2** | Legacy delegate |
| `RUNBOOK` mirror + legacy curls | **1** / **2** | |
| `src/legacy/api/client.ts` | **3** | Parked |
| `legacy-smoke.mjs` | **2** | Compatibility smoke |
| `test_api_slice1.py` | **4** | |
| `POSTGRES_API_DASHBOARD_PLAN.md` | **5** | Historical plan; add deprecation banner in 4B |

### `/classification/*`

| Location | Cat | Notes |
|----------|-----|-------|
| `postgres_dashboard_api/classification.py` + mirror routes | **1** | |
| `origenlab_api/routers/classification.py` | **2** | |
| RUNBOOK / parity smoke | **1** / **2** | |
| `src/legacy/` components (if any) | **3** | Parked tabs |
| `test_api_classification.py` | **4** | |

### `/commercial/purchase-events`

| Location | Cat | Notes |
|----------|-----|-------|
| `postgres_dashboard_api/commercial_purchase.py` + mirror | **1** | |
| `origenlab_api/routers/commercial.py` | **2** | |
| `test_api_commercial_purchase_events.py` | **4** | |
| `dashboard0Safety` forbidden `/commercial/purchase` | **6** | Active Today guard |

### `/meta/dashboard-sync`, `/outbound/*`

| Location | Cat | Notes |
|----------|-----|-------|
| Shared modules + mirror `meta` / `outbound` routes | **1** | |
| Legacy routers | **2** | |
| RUNBOOK / mirror smokes | **1** / **2** | |
| `test_api_slice1.py` (outbound slices) | **4** | |

### `/contacts` and `/organizations` (mart **list**, not operator detail)

| Location | Cat | Notes |
|----------|-----|-------|
| `postgres_dashboard_api/mart_lists.py` + `/mirror/contacts` | **1** | |
| `origenlab_api/routers/contacts.py` / `organizations.py` | **2** | |
| `src/legacy/api/client.ts` — `GET /contacts` list | **3** | Not `GET /contacts/{email}` |
| `apps/api/routes/contacts.py` — `/contacts/{email}` | **6** | Operator detail; different contract |
| `vite.config.ts` proxy `/contacts` | **6** | Proxies operator detail to `:8001` |
| `dashboard0Safety` `"/contacts"` fragment | **6** | Forbidden in **active** src (legacy path string) |

---

## `ORIGENLAB_API_BASE_URL` / `VITE_ORIGENLAB_API_BASE_URL`

| Consumer | Default / behavior | Cat |
|----------|-------------------|-----|
| `streamlit_api_preview.py` | Default **`http://127.0.0.1:8001`**; `:8000` → legacy paths without `/mirror` | **1** |
| `email-pipeline/.env.example` | Commented `:8001` preferred, `:8000` legacy | **1** / **2** |
| `dashboard/vite.config.ts` | Proxy target **`8001`** when env unset | **1** |
| `dashboard/operatorClient.ts` | Production requires env; dev uses proxy | **1** |
| `dashboard/legacy/api/client.ts` | Falls back to **`8000`** | **3** |
| `legacy-smoke.mjs` | `VITE_*` or **`8000`** | **2** |

**Stale doc (Phase 4B):** `API-3_RELOCATION_AUDIT.md` Streamlit row still says default `:8000` — code is `:8001` since Phase 3A.

---

## `origenlab_api` tree (`apps/email-pipeline/src/origenlab_api`)

| Role | Cat | Delete? |
|------|-----|---------|
| Legacy FastAPI app (routers, deps, schemas re-exports) | **2** | **No** |
| `services/queries.py` — re-exports `mart_lists` | **1** | **No** (thin shim) |
| `tests/test_api_*.py` in email-pipeline | **4** | **No** until mirror-only CI |
| `apps/api/tests/test_import_guard.py` | **4** | Ensures **apps/api** wins import |
| `mirror/tests/test_mirror_import_guard.py` | **4** | Mirror must not import legacy package |

---

## `smoke:legacy` / `legacy-smoke` / `smoke:mirror`

| Script | Port / paths | Cat | Phase 4B |
|--------|--------------|-----|----------|
| `npm run smoke:mirror` | `:8001` `/mirror/*` | **1** | Document as **preferred** in operator runbooks |
| `npm run smoke:legacy` | `:8000` `/health`, `/dashboard/summary` | **2** | **Keep** until Phase 6 |
| `mirror_parity_smoke.py` | Both hosts | **2** | Keep for deprecation window |
| v1 freeze checklist | `smoke-v1` only (operator routes) | **1** | No change |

---

## `apps/dashboard/src/legacy`

| Item | Cat | Notes |
|------|-----|-------|
| Entire `src/legacy/` tree | **3** | Not imported by `App.tsx` / Today |
| `vite.config.ts` `exclude: src/legacy/**` from tests | **3** | |
| `dashboard0Safety.test.ts` | **4** | Ensures active code does not import legacy panels |
| `legacy/README.md` | **3** | Parked documentation |

**Phase 4B (optional):** If product revives multi-tab UI, add `legacy/api/mirrorClient.ts` pointing at `:8001` `/mirror/*` instead of editing parked `:8000` client in place.

---

## Active Dashboard Today (verification)

| Check | Result |
|-------|--------|
| Calls `/mirror/*` | **No** |
| Depends on `:8000` | **No** (warns if dev env misconfigured) |
| Operator routes on `:8001` | `/health`, `/operator/status`, `/cases/warm`, `/opportunities/equipment`, `/contacts/{email}`, `/emails/recent` |
| v1 freeze CI | `smoke-v1` + policy tests only |

---

## Phase 4B cleanup (done)

See [API-3_PHASE4B_CLEANUP.md](./API-3_PHASE4B_CLEANUP.md): architecture plan banner, Streamlit tests, parked `src/legacy/README.md`, **`api3_phase6_grep_gate.sh`** + allowlist (not required to pass yet).

**Not in Phase 4B (Phase 6 only):**

- Delete `apps/email-pipeline/src/origenlab_api`
- Remove `smoke:legacy` or `:8000` uvicorn from RUNBOOK
- Remove legacy route handlers

---

## Phase 6 zero-reference gate (preview)

Deletion allowed only when grep shows **no** hits outside:

- `apps/email-pipeline/src/origenlab_api/**` (the tree itself)
- Deprecated RUNBOOK section (or moved to archive doc)
- `test_api_*` / parity / `legacy-smoke` (removed or repointed)
- Parked `src/legacy/` (removed or repointed)

**Current verdict:** **~22 intentional :8000 references** remain → **do not delete**.

---

## Related documents

| Doc | Role |
|-----|------|
| [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md) | Original consumer inventory |
| [API-3_PHASE3C_DEPRECATION.md](./API-3_PHASE3C_DEPRECATION.md) | Deprecation headers |
| [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) | Route matrix |
| [API-3_PHASE3B_LIVE_PARITY_REPORT.md](./API-3_PHASE3B_LIVE_PARITY_REPORT.md) | Live dual-server proof |
