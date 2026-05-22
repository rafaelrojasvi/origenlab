# API-3 Phase 5B — Phase 6 legacy deletion PR plan

**Status:** Executed in Phase 6 (2026-05). Legacy `:8000` tree removed — see [API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md](./API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md).  
**Inputs:** [API-3_PHASE5A_DELETION_READINESS.md](./API-3_PHASE5A_DELETION_READINESS.md), [API-3_PHASE4A_REFERENCE_AUDIT.md](./API-3_PHASE4A_REFERENCE_AUDIT.md), `api3_phase6_grep_gate.sh`, `api3_phase6_grep_allowlist.txt`  
**Goal:** One controlled Phase 6 PR that removes the deprecated **email-pipeline `:8000`** API without touching Dashboard Today or `apps/api` operator routes.

---

## Executive summary

| Item | Phase 5B (now) | Phase 6 PR (later) |
|------|----------------|---------------------|
| Delete `apps/email-pipeline/src/origenlab_api/` | **No** | **Yes** (entire tree) |
| Remove `smoke:legacy` | **No** | **Yes** |
| Change Dashboard Today | **No** | **No** |
| Strict grep gate | Report-only / passes via broad allowlist | Must pass with **minimal** allowlist |
| Proceed to Phase 6? | **Not yet** — execute this plan when product signs off |

---

## 1. Phase 6 PR scope (single PR)

**Title (suggested):** `API-3 Phase 6: remove email-pipeline legacy :8000 API`

**Pre-merge checklist:** Section 6 (breakage) must be all green; Section 5 (test plan) all pass.

### 1.1 Delete — legacy implementation (18 files)

Remove directory **`apps/email-pipeline/src/origenlab_api/`** in full:

```
apps/email-pipeline/src/origenlab_api/__init__.py
apps/email-pipeline/src/origenlab_api/config.py
apps/email-pipeline/src/origenlab_api/db.py
apps/email-pipeline/src/origenlab_api/deps.py
apps/email-pipeline/src/origenlab_api/deprecation.py
apps/email-pipeline/src/origenlab_api/main.py
apps/email-pipeline/src/origenlab_api/schemas.py
apps/email-pipeline/src/origenlab_api/routers/__init__.py
apps/email-pipeline/src/origenlab_api/routers/classification.py
apps/email-pipeline/src/origenlab_api/routers/commercial.py
apps/email-pipeline/src/origenlab_api/routers/contacts.py
apps/email-pipeline/src/origenlab_api/routers/dashboard.py
apps/email-pipeline/src/origenlab_api/routers/health.py
apps/email-pipeline/src/origenlab_api/routers/meta.py
apps/email-pipeline/src/origenlab_api/routers/organizations.py
apps/email-pipeline/src/origenlab_api/routers/outbound.py
apps/email-pipeline/src/origenlab_api/services/__init__.py
apps/email-pipeline/src/origenlab_api/services/queries.py
```

**Also update packaging:** `apps/email-pipeline/pyproject.toml` — remove `"src/origenlab_api"` from `[tool.hatch.build.targets.wheel] packages`.

### 1.2 Delete — legacy API tests (`:8000` only)

| File | Why |
|------|-----|
| `apps/email-pipeline/tests/test_api_slice1.py` | Legacy app HTTP contract |
| `apps/email-pipeline/tests/test_api_classification.py` | Legacy classification routes |
| `apps/email-pipeline/tests/test_api_commercial_purchase_events.py` | Legacy commercial routes |
| `apps/email-pipeline/tests/test_api_meta.py` | Legacy meta routes |
| `apps/email-pipeline/tests/test_api_cors.py` | Legacy CORS on `:8000` app |
| `apps/email-pipeline/tests/test_api_deprecation.py` | Deprecation headers on legacy app |

**Keep / extend:** mirror coverage in `apps/api/tests/mirror/test_mirror_*.py` (already assert `/mirror/*` behavior).

### 1.3 Delete — dashboard legacy smoke

| File / entry | Action |
|--------------|--------|
| `apps/dashboard/scripts/legacy-smoke.mjs` | **Delete** |
| `apps/dashboard/package.json` → `"smoke:legacy"` | **Remove** script entry |

### 1.4 Delete or rewrite — dual-server `:8000` tooling

| Artifact | Phase 6 action |
|----------|----------------|
| `apps/api/scripts/run_mirror_dual_server_parity.sh` | **Rewrite** mirror-only (single `uvicorn` on `:8001`) or **delete** if `mirror_parity_smoke.py` + CI mirror tests suffice |
| `apps/api/scripts/mirror_parity_smoke.py` | Remove `--legacy-base` / dual-compare; **mirror-only** GET smoke |
| `apps/api/docs/API-3_PHASE3B_LIVE_PARITY_REPORT.md` | Add completion note; archive dual-server section |

### 1.5 Delete / archive — deprecation-only artifacts

| Artifact | Action |
|----------|--------|
| `apps/email-pipeline/src/origenlab_api/deprecation.py` | Gone with tree |
| Legacy deprecation middleware on `:8000` app | Gone with tree |
| `apps/api/tests/mirror/test_mirror_phase3c_deprecation.py` | **Remove** or replace with “legacy removed” policy test |
| RUNBOOK “Legacy Slice-1 API (:8000)” uvicorn block | **Remove** or move to `docs/archive/api3-legacy-8000.md` |
| RUNBOOK deprecated `curl :8000/...` subsection | **Remove** or archive |
| `apps/email-pipeline/.env.example` commented `:8000` override | **Remove** legacy comment lines |

### 1.6 Update — Streamlit / sync (no `:8000` branch)

| File | Change |
|------|--------|
| `apps/email-pipeline/src/origenlab_email_pipeline/streamlit_api_preview.py` | Remove `norm.endswith(":8000")` branch; **`:8001` `/mirror/*` only** |
| `apps/email-pipeline/tests/test_streamlit_api_preview.py` | Remove `test_api_preview_paths_legacy_on_8000` |
| `apps/email-pipeline/src/origenlab_email_pipeline/dashboard_postgres_sync.py` | Drop trailing legacy `:8000` curl hint (keep `:8001` mirror hints) |

### 1.7 Update — docs (repoint or archive, do not delete API-3 history)

| Doc | Change |
|-----|--------|
| `apps/email-pipeline/docs/RUNBOOK.md` | Remove live `:8000` uvicorn + deprecated curls; point operators to `:8001` `/mirror/*` only |
| `apps/email-pipeline/docs/architecture/POSTGRES_API_DASHBOARD_PLAN.md` | Strip “run on :8000” deployment steps; keep historical note in archive link |
| `apps/api/README.md` | Remove “legacy still on 8000” coexistence; document mirror-only |
| `apps/api/docs/API-3_*.md` | Add **Phase 6 complete** banner at top of series; no false “do not delete” |
| `apps/dashboard/README.md` | Remove `smoke:legacy` references; keep `smoke:mirror` |
| `apps/dashboard/src/legacy/README.md` | State legacy **server** removed; parked UI paths are historical |

**New (recommended):** `apps/api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md` — what was deleted and replacement URLs.

### 1.8 Optional product decision — parked dashboard UI

| Path | Options (pick one in Phase 6 PR) |
|------|----------------------------------|
| `apps/dashboard/src/legacy/**` | **A)** Delete tree (recommended if no revival planned). **B)** Repoint `legacy/api/client.ts` to `:8001` `/mirror/*` and keep excluded from `npm test`. |

**Do not** mount parked UI in `App.tsx` without explicit product approval.

### 1.9 Allowlist — replace with minimal target

**Phase 5B:** Active allowlist **unchanged** (broad; gate report-only).  
**Phase 6 PR:** Replace `api3_phase6_grep_allowlist.txt` with preview target (see `api3_phase6_grep_allowlist.phase6_target.txt`):

```
# Post-deletion: archive docs only (example)
apps/api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md
apps/email-pipeline/docs/archive/
```

**Remove these allowlist prefixes in Phase 6** (because files/refs are gone):

- `apps/email-pipeline/src/origenlab_api/`
- `apps/email-pipeline/tests/` (for deleted `test_api_*` only — keep prefix if other tests still mention routes in comments; prefer delete refs)
- `apps/dashboard/scripts/legacy-smoke.mjs`
- `smoke:legacy` hits (gone from `package.json`)
- Broad `apps/api/docs/` prefix — **shrink**: migrate API-3 docs to archive subfolder or strip live `:8000` examples

**Optional gate hardening (Phase 6 PR):** add pattern `apps/email-pipeline/src/origenlab_api` to `api3_phase6_grep_gate.sh` so any surviving path reference fails strict mode.

---

## 2. Must stay (do not delete in Phase 6)

| Asset | Reason |
|-------|--------|
| **`apps/api/src/origenlab_api/**`** | Operator Dashboard API (`:8001`) — **different package tree** from email-pipeline legacy |
| **`apps/api/src/origenlab_api/mirror/**`** | Postgres mirror reporting (`GET /mirror/*`) |
| **`origenlab_email_pipeline/postgres_dashboard_api/`** | Shared SQL/types; imported by mirror routers |
| **`origenlab_email_pipeline/dashboard_postgres_sync.py`** | Mirror sync CLI (update hints only) |
| **Dashboard Today** | `TodayPage`, `operatorClient.ts` — `/health`, `/operator/status`, `/cases/warm`, `/opportunities/equipment`, `/contacts/{email}`, `/emails/recent` |
| **`apps/dashboard/scripts/smoke-v1.mjs`**, freeze checklist | v1 operator smoke on `:8001` |
| **`npm run smoke:mirror`** | `mirror-smoke.mjs` — `:8001` `/mirror/*` only |
| **`apps/api/tests/mirror/`** | Mirror contract tests (update parity tests to mirror-only) |
| **Import guard** | `test_mirror_import_guard.py` — keep forbidding email-pipeline `origenlab_api` imports in mirror |

---

## 3. Phase 6 test plan (exact commands)

Run from repo root after Phase 6 code changes. **No** Gmail / production or scratch Postgres mutation.

| Step | Command | Expect |
|------|---------|--------|
| 1 | `cd apps/api && uv run pytest tests -q` | All pass |
| 2 | `cd apps/api && uv run pytest tests/mirror -q` | All pass (parity tests updated to mirror-only) |
| 3 | `cd apps/email-pipeline && uv run --group ui pytest tests/test_streamlit_api_preview.py tests/test_doc_dashboard_runbook.py -q` | Pass (legacy `:8000` test removed) |
| 4 | `cd apps/dashboard && ./scripts/run-v1-freeze-checklist.sh` | **OK** (unchanged Today contract) |
| 5 | `apps/api/scripts/api3_phase6_grep_gate.sh` | **Exit 0**, unallowlisted **0**, minimal allowlist |
| 6 | `apps/api/scripts/api3_phase5a_deletion_audit.sh` | Unallowlisted **0**; legacy `main.py` **absent** |
| 7 (optional) | `cd apps/dashboard && npm run smoke:mirror` | Pass with `apps/api` on `:8001` + disposable Postgres if matrix doc requires |
| 8 (optional) | `cd apps/api && ./scripts/run_mirror_dual_server_parity.sh` | **Removed** or mirror-only variant passes |

**Policy tests to add/update in Phase 6 PR:**

- Legacy tree **missing** (`test_mirror_phase6_legacy_removed.py` or extend phase 5A test inverted).
- `smoke:legacy` **absent** from `package.json`.
- `test_mirror_import_guard` still passes.

---

## 4. Suggested PR commit order

1. **Shared behavior:** ensure mirror tests green before deleting legacy.
2. **Delete** `apps/email-pipeline/src/origenlab_api/` + pyproject wheel package entry.
3. **Delete** `test_api_*.py` (legacy) + `test_api_deprecation.py`.
4. **Delete** `legacy-smoke.mjs`, remove `smoke:legacy`.
5. **Rewrite** parity scripts / remove `:8000` uvicorn from RUNBOOK.
6. **Update** Streamlit + sync hints (`:8001` only).
7. **Update** docs + add `API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md`.
8. **Shrink** `api3_phase6_grep_allowlist.txt` to phase6 target.
9. **Optional:** delete or repoint `apps/dashboard/src/legacy/`.
10. Run Section 3 test plan; attach audit output to PR description.

---

## 5. Breakage checklist (run before merge)

Use ripgrep from repo root. **Must be empty** (or only under `docs/archive/`) before Phase 6 merge.

| # | Question | Command / check | Phase 5B (now) |
|---|----------|-----------------|----------------|
| 1 | Anything still **import** email-pipeline `origenlab_api`? | `rg 'from origenlab_api|import origenlab_api' apps --glob '!apps/email-pipeline/src/origenlab_api/**' --glob '!apps/api/src/**'` | Mirror guard OK; legacy tests import legacy app |
| 2 | Docs tell operators to run **email-pipeline uvicorn :8000**? | `rg 'uvicorn origenlab_api.main' apps/email-pipeline/docs` | RUNBOOK still has deprecated block — **remove in Phase 6** |
| 3 | `package.json` exposes **`smoke:legacy`**? | `rg 'smoke:legacy' apps/dashboard/package.json` | **Yes** (intentional until Phase 6) |
| 4 | Tests expect **deprecation headers** on `:8000`? | `rg 'X-OrigenLab-Deprecated' apps --glob '*test*'` | `test_api_deprecation.py`, `test_mirror_phase3c_deprecation.py` — **remove/update in Phase 6** |
| 5 | Scripts **require** `:8000` server running? | `rg '127\.0\.0\.1:8000|localhost:8000' apps/api/scripts apps/dashboard/scripts` | dual-server + legacy-smoke — **rewrite/delete in Phase 6** |
| 6 | **apps/api** mirror imports legacy modules? | `uv run pytest apps/api/tests/mirror/test_mirror_import_guard.py -q` | **Pass** |
| 7 | Dashboard **Today** calls `:8000` or `/mirror/*`? | `rg ':8000|/mirror/' apps/dashboard/src/api/operatorClient.ts apps/dashboard/src/pages/TodayPage.tsx` | **No** |
| 8 | Legacy tree exists? | `test -f apps/email-pipeline/src/origenlab_api/main.py` | **Yes** (required until Phase 6) |

---

## 6. Allowlist policy (Phase 5B)

| Item | Action in 5B |
|------|----------------|
| `api3_phase6_grep_allowlist.txt` | **Not shrunk** — deletion not performed; shrinking would break report-only audits |
| `api3_phase6_grep_allowlist.phase6_target.txt` | **Added** as Phase 6 target preview (inactive) |
| Strict gate | Continues to pass with 0 unallowlisted (broad allowlist) |
| Enforcement | **Report-only** until Phase 6 PR lands |

After Phase 6, expected inventory: **&lt;10** allowlisted hits (archive docs only).

---

## 7. Phase 5B verification (no deletion)

| Check | Status |
|-------|--------|
| This plan exists | **Yes** |
| Legacy tree present | **Yes** |
| `smoke:legacy` present | **Yes** |
| Dashboard Today unchanged | **Yes** |
| Mirror routes on `apps/api` | **Yes** (13 paths) |

---

## 8. Recommendation

| Proceed to Phase 6? | **Not yet** |
|---------------------|-------------|
| **When ready** | Product/operator sign-off + breakage checklist (Section 5) all green + test plan (Section 3) attached to PR |
| **Next step** | Open Phase 6 PR using Section 1 file list and Section 4 commit order |

---

## Related

| Doc | Role |
|-----|------|
| [API-3_PHASE5A_DELETION_READINESS.md](./API-3_PHASE5A_DELETION_READINESS.md) | Dry-run gate + inventory |
| [API-3_PHASE4A_REFERENCE_AUDIT.md](./API-3_PHASE4A_REFERENCE_AUDIT.md) | Reference categories |
| `api3_phase6_grep_allowlist.phase6_target.txt` | Post-deletion allowlist preview |
| `api3_phase5a_deletion_audit.sh` | Pre/post deletion reporter |
