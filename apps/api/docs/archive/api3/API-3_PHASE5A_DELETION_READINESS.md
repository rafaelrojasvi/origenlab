# API-3 Phase 5A — Deletion-readiness dry run

**Date:** 2026-05-18  
**Method:** Strict `api3_phase6_grep_gate.sh` + `api3_phase5a_deletion_audit.sh` hit inventory  
**Action taken:** None — no files deleted, no routes removed.

---

## Executive summary

| Question | Answer |
|----------|--------|
| **Strict grep gate (route/port patterns)** | **PASS** — 0 unallowlisted hits |
| **Semantic zero-reference for Phase 6 deletion** | **NOT met** — **576** allowlisted legacy references remain (dry-run inventory) |
| **Safe to delete `apps/email-pipeline/src/origenlab_api` now** | **No** |
| **Dashboard Today uses `:8000` or `/mirror/*`** | **No** — operator `:8001` only |
| **`apps/api` `/mirror/*` routes** | **Present** — 13 OpenAPI paths (parity matrix) |
| **Write endpoints added** | **No** — mirror routes GET-only |

**Recommendation:** Proceed to **Phase 5B** (tighten gate scope, shrink allowlist, repoint or archive remaining docs) before **Phase 6** (delete legacy tree, remove `smoke:legacy`, drop dual-server `:8000` orchestration).

---

## 1. Strict Phase 6 grep gate result

Command (2026-05-18):

```bash
apps/api/scripts/api3_phase6_grep_gate.sh
```

| Metric | Value |
|--------|-------|
| Exit code | **0** |
| Unallowlisted hits | **0** |
| Message | `OK: no legacy references outside allowlist` |

Patterns scanned: `127.0.0.1:8000`, `localhost:8000`, `port 8000`, legacy route families (`/dashboard/summary`, `/classification/`, `/commercial/purchase-events`, `/meta/dashboard-sync`, `/outbound/`), `smoke:legacy`, `legacy-smoke`, mart-list/contact patterns.

**Important:** The gate passes because intentional references are covered by `api3_phase6_grep_allowlist.txt` (path-prefix allowlist). Passing the gate is **necessary but not sufficient** for deletion.

---

## 2. Allowlisted vs unallowlisted inventory

From `apps/api/scripts/api3_phase5a_deletion_audit.sh` (same patterns + legacy tree path):

| Bucket | Approx. count |
|--------|----------------|
| Unique pattern hits (deduped) | **576** |
| **Allowlisted** | **576** |
| **Unallowlisted** (route/port patterns only) | **0** (strict gate) |
| References to `apps/email-pipeline/src/origenlab_api` | **47** (all under allowlisted prefix) |

### Top allowlist prefixes (why hits remain)

| Prefix | Hits (5A audit) | Role until Phase 6 |
|--------|-----------------|---------------------|
| `apps/api/docs/` | 229 | Migration narrative, parity reports |
| `apps/api/tests/` | 98 | Mirror + legacy parity tests |
| `apps/email-pipeline/docs/` | 60 | RUNBOOK deprecated + mirror curls |
| `apps/api/scripts/` | 54 | Dual-server parity, grep gate, smoke helpers |
| `apps/email-pipeline/tests/` | 44 | `test_api_*`, deprecation, Streamlit compat |
| `apps/dashboard/src/legacy/` | 30 | Parked pre-v1 client (not mounted) |
| `apps/email-pipeline/src/origenlab_api/` | (47 path refs) | **Legacy implementation (delete target)** |
| `apps/dashboard/scripts/` | incl. `legacy-smoke.mjs` | `smoke:legacy` |

---

## 3. Is the zero-reference gate met?

| Gate type | Met? | Notes |
|-----------|------|-------|
| **Mechanical** (no hits outside allowlist) | **Yes** | Current allowlist is broad by design (Phases 4B–5A) |
| **Semantic** (no runtime need for legacy `:8000` API) | **No** | Legacy package, smokes, parity scripts, and compat tests still required |
| **Tree deletion** (safe to remove `origenlab_api` under email-pipeline) | **No** | 18 Python modules; delegates still served on `:8000` |

Phase 4A estimated **~22 intentional `:8000` host references** outside production Dashboard; those remain **allowlisted**, not eliminated.

---

## 4. Remaining intentional legacy references (by category)

| Cat | What | Why it remains |
|-----|------|----------------|
| **A — Legacy implementation** | `apps/email-pipeline/src/origenlab_api/**` (18 modules) | Deprecated API still served on `:8000` during window |
| **B — Deprecation + compat** | `deprecation.py`, middleware, RUNBOOK `:8000` uvicorn block | Operator visibility + header contract |
| **C — Dual-server proof** | `run_mirror_dual_server_parity.sh`, `mirror_parity_smoke.py --legacy-base` | Proves legacy↔mirror parity before cutover |
| **D — Smokes** | `npm run smoke:legacy`, `legacy-smoke.mjs` | Validates deprecated stack until Phase 6 |
| **E — Parked UI** | `apps/dashboard/src/legacy/**` | Not mounted; historical client on legacy paths |
| **F — Tests** | `test_api_slice1.py`, `test_api_classification.py`, `test_api_deprecation.py`, Streamlit `:8000` path tests | Lock compat behavior |
| **G — Docs / audit** | API-3 series, `POSTGRES_API_DASHBOARD_PLAN.md`, Phase 4A audit | Migration record + operator guidance |
| **H — Streamlit / sync** | `streamlit_api_preview.py` (`:8000` when base ends with `:8000`), `dashboard_postgres_sync.py` hints | Explicit legacy mode only |

**Not legacy (do not delete in Phase 6):** `apps/api/src/origenlab_api/**` — this is the **operator Dashboard API** package name (same import path, different tree from email-pipeline legacy).

---

## 5. Required until Phase 6 deletion

Must keep until sign-off and deletion PR:

1. Full tree `apps/email-pipeline/src/origenlab_api/`
2. `:8000` route handlers (via legacy FastAPI app)
3. `smoke:legacy` + `legacy-smoke.mjs`
4. Dual-server parity script + legacy base URL in `mirror_parity_smoke.py`
5. email-pipeline `test_api_*` + `test_api_deprecation.py`
6. Deprecation headers middleware
7. Allowlist entries for (A)–(H) above

**Not required for production Dashboard Today** (already satisfied): any runtime call from `operatorClient.ts` to `:8000` or `/mirror/*`.

---

## 6. What Phase 6 must remove or repoint

| Artifact | Phase 6 action |
|----------|----------------|
| `apps/email-pipeline/src/origenlab_api/` | **Delete** tree after zero semantic refs |
| RUNBOOK `:8000` uvicorn + deprecated curl blocks | Remove or move to `docs/archive/` |
| `apps/dashboard/scripts/legacy-smoke.mjs`, `smoke:legacy` | Remove script + `package.json` script |
| `run_mirror_dual_server_parity.sh` legacy uvicorn leg | Drop `:8000` server; mirror-only smoke |
| `mirror_parity_smoke.py --legacy-base` | Remove dual compare; keep mirror-only |
| `apps/dashboard/src/legacy/` | Delete or repoint to `/mirror/*` if product revives UI |
| `test_api_slice1.py`, `test_api_classification.py`, `test_api_commercial_purchase_events.py` | Delete or move assertions to mirror tests only |
| Streamlit `:8000` branch in `api_preview_paths()` | Remove; `:8001` only |
| `api3_phase6_grep_allowlist.txt` | Shrink to archive-only paths |
| Allowlist prefix `apps/email-pipeline/src/origenlab_api/` | Remove entry (tree gone) |

**Keep:** `apps/api` `/mirror/*`, shared `postgres_dashboard_api/`, operator Today routes, `smoke:mirror`.

---

## 7. Tests / smokes / docs that would change in Phase 6

| Area | Current | Phase 6 change |
|------|---------|----------------|
| `apps/email-pipeline/tests/test_api_*.py` | Hit legacy app on `:8000` | Removed or replaced by mirror-only |
| `apps/email-pipeline/tests/test_api_deprecation.py` | Asserts deprecation headers | Removed with legacy app |
| `apps/api/tests/mirror/test_mirror_phase2_parity.py` | Legacy↔mirror pairs | Drop legacy side; mirror-only contract tests |
| `apps/api/scripts/run_mirror_dual_server_parity.sh` | Two uvicorns | Single `:8001` orchestration |
| `apps/dashboard/package.json` | `smoke:legacy` | Removed |
| `apps/dashboard/scripts/legacy-smoke.mjs` | Deleted | |
| `apps/api/scripts/api3_phase6_grep_gate.sh` | Broad allowlist | Tight patterns; minimal allowlist |
| API-3 docs | Describe coexistence | Add Phase 6 completion note / archive |
| `POSTGRES_API_DASHBOARD_PLAN.md` | Historical `:8000` sections | Archive or strip legacy deployment |
| `test_streamlit_api_preview.py` | `:8000` legacy path test | Remove legacy branch test |

**Unchanged in Phase 6 (operator product):** `TodayPage`, `operatorClient.ts`, v1 freeze checklist smokes (`smoke`, `smoke:sqlite`, `smoke:postgres`), `GET /contacts/{email}`.

---

## 8. Active system verification (Phase 5A)

| Check | Status |
|-------|--------|
| `apps/dashboard/src/api/operatorClient.ts` — no `:8000`, no `/mirror/*` | **OK** |
| `apps/email-pipeline/src/origenlab_api/main.py` exists | **OK** (legacy not deleted) |
| `apps/api` mirror router mounted; 13 `/mirror/*` paths | **OK** |
| Mirror routes GET-only (`test_mirror_phase5a_deletion_readiness.py`) | **OK** |
| `smoke:legacy` still in `package.json` | **OK** (not removed) |

---

## 9. Deletion safety verdict

| Verdict | Detail |
|---------|--------|
| **Strict grep gate** | **PASS** (0 unallowlisted) |
| **Deletion safe now** | **NO** |
| **Reason** | Legacy package, smokes, parity tooling, and hundreds of allowlisted references still define the deprecation window contract |

---

## 10. Recommendation: Phase 5B vs Phase 6

### Phase 5B (next, before deletion)

**Done:** [API-3_PHASE5B_DELETION_PR_PLAN.md](./API-3_PHASE5B_DELETION_PR_PLAN.md) — exact Phase 6 file list, test plan, breakage checklist. Allowlist **not shrunk** until deletion PR; see `api3_phase6_grep_allowlist.phase6_target.txt`.

### Phase 6 (deletion)

1. Delete `apps/email-pipeline/src/origenlab_api/`
2. Remove `smoke:legacy`, dual-server legacy leg, legacy email-pipeline API tests
3. Update RUNBOOK / sync hints / Streamlit to `:8001` only
4. Minimal allowlist; strict gate must pass with **near-zero** allowlisted hits

---

## Related

| Doc / script | Role |
|--------------|------|
| [API-3_PHASE4A_REFERENCE_AUDIT.md](./API-3_PHASE4A_REFERENCE_AUDIT.md) | Reference classification |
| [API-3_PHASE4B_CLEANUP.md](./API-3_PHASE4B_CLEANUP.md) | Gate + allowlist introduction |
| `apps/api/scripts/api3_phase6_grep_gate.sh` | Strict enforcement |
| `apps/api/scripts/api3_phase5a_deletion_audit.sh` | This dry-run reporter |
