# API-3 Phase 2 — Mirror parity checklist (frozen)

**Status:** Phase 2 **frozen** (2026-05). Phase 1 relocation complete; this document is the sign-off matrix before Streamlit/RUNBOOK cutover (Phase 3+).

**Scope:** Docs, tests, and optional dual-server smoke only. No new mirror routes unless a gap is discovered. Legacy `apps/email-pipeline/src/origenlab_api` **not deleted**. Dashboard Today routes **unchanged**. No write endpoints.

**Enforcement:** Route pairs are duplicated in code as `tests/mirror/parity_routes.py` and validated by `tests/mirror/test_mirror_phase2_parity.py`.

---

## Parity matrix (legacy :8000 → mirror :8001)

| # | Legacy GET (port 8000) | Mirror GET (port 8001) | Query / path notes | Phase 1 |
|---|------------------------|-------------------------|-------------------|---------|
| 1 | `/health/dependencies` | `/mirror/health/dependencies` | — | 1A |
| 2 | `/meta/dashboard-sync` | `/mirror/meta/dashboard-sync` | — | 1A |
| 3 | `/dashboard/summary` | `/mirror/dashboard/summary` | `scope=canonical` \| `archive` | 1B |
| 4 | `/classification/summary` | `/mirror/classification/summary` | — | 1E |
| 5 | `/classification/recent` | `/mirror/classification/recent` | `label`, `limit` | 1E |
| 6 | `/classification/actions` | `/mirror/classification/actions` | — | 1E |
| 7 | `/commercial/purchase-events` | `/mirror/commercial/purchase-events` | `limit` 1–100 | 1F |
| 8 | `/commercial/purchase-events/{id}` | `/mirror/commercial/purchase-events/{event_id}` | Path param name `event_id` on mirror; same row semantics | 1F |
| 9 | `/contacts` | `/mirror/contacts` | `limit`, `offset`, `domain`, `q`, `scope` — **mart list only** | 1G |
| 10 | `/organizations` | `/mirror/organizations` | same pagination/filter params | 1G |
| 11 | `/outbound/suppressions/emails` | `/mirror/outbound/suppressions/emails` | pagination | 1D |
| 12 | `/outbound/contact-state` | `/mirror/outbound/contact-state` | pagination | 1D |
| 13 | `/outbound/readiness` | `/mirror/outbound/readiness` | `max_staleness_days` (read-only report) | 1C |

**Total legacy read routes mirrored:** 13 pairs (14 path patterns including commercial detail).

---

## Intentional exceptions

| Legacy route | Mirror alias | Active :8001 route | Notes |
|--------------|--------------|-------------------|--------|
| `GET /health` | **None** | `GET /health` | Legacy returns Slice-1 `HealthResponse` (`status`, `read_only`). Operator `GET /health` returns `ok`, `mode`, `backend`, `postgres_configured`. **Different contracts by design.** |
| `GET /contacts` | `GET /mirror/contacts` | `GET /contacts/{email}` | Operator **detail** is SQLite/postgres intel; mirror **list** is paginated mart. Do not merge paths. |

---

## Shared implementation

All mirrored handlers delegate to `origenlab_email_pipeline.postgres_dashboard_api.*`. Legacy routers in `apps/email-pipeline/src/origenlab_api` remain thin wrappers. Mirror routers live under `apps/api/src/origenlab_api/mirror/`.

---

## Policy checks (automated)

| Check | Test module |
|-------|-------------|
| Every documented mirror path in OpenAPI | `test_mirror_phase2_parity.py` |
| Mirror routes GET-only | `test_mirror_no_write_policy.py`, `test_mirror_phase2_parity.py` |
| No `/mirror/health` alias for legacy `/health` | `test_mirror_phase2_parity.py` |
| `/contacts/{email}` distinct from `/mirror/contacts` | `test_mirror_mart_lists.py`, `test_mirror_phase2_parity.py` |
| Active dashboard does not call `/mirror/*` | `test_mirror_phase2_parity.py`, dashboard `dashboard0Safety.test.ts` |
| Legacy tree not deleted | `test_mirror_phase2_parity.py` |
| Mirror does not import legacy `origenlab_api` | `test_mirror_import_guard.py` |

---

## Optional live parity smoke (both servers running)

Requires:

1. Legacy API: `cd apps/email-pipeline && uv run uvicorn origenlab_api.main:app --port 8000`
2. Mirror API: `cd apps/api && ORIGENLAB_POSTGRES_URL=… uv run uvicorn origenlab_api.main:app --port 8001`
3. **Disposable Postgres only** — do not point at production or scratch mutation targets.

```bash
cd apps/api
uv run python scripts/mirror_parity_smoke.py \
  --legacy-base http://127.0.0.1:8000 \
  --mirror-base http://127.0.0.1:8001
```

The script is **GET-only**, compares HTTP status and top-level JSON keys (not full row equality). Commercial detail uses `--event-id` when both sides should return 200 for the same id.

Exit `2` if either server is unreachable. Exit `1` on status/key mismatch.

---

## Phase 2 sign-off

| Item | Result |
|------|--------|
| All Phase 1 legacy read routes have `/mirror/*` twin | **Yes** (13 pairs) |
| Legacy `/health` intentionally unmirrored | **Yes** |
| Operator Today routes unchanged | **Yes** |
| Dashboard calls `/mirror/*` | **No** (Today unchanged; Phase 3A repoints docs/smokes only) |
| Streamlit / RUNBOOK repointed | **Phase 3A** — prefer :8001 `/mirror/*` in operator docs |
| Legacy tree deleted | **No** |
| Write endpoints added | **No** |

---

## Phase 4B cleanup + Phase 6 gate prep

| Item | Result |
|------|--------|
| `POSTGRES_API_DASHBOARD_PLAN.md` banner | **Done** |
| Streamlit mirror path tests | **Done** |
| Parked legacy README | **Done** |
| `api3_phase6_grep_gate.sh` | **Added** (expected fail until Phase 6) |
| Doc | [API-3_PHASE4B_CLEANUP.md](./API-3_PHASE4B_CLEANUP.md) |

---

## Phase 4A reference audit

| Item | Result |
|------|--------|
| Grep audit doc | [API-3_PHASE4A_REFERENCE_AUDIT.md](./API-3_PHASE4A_REFERENCE_AUDIT.md) |
| Delete legacy tree | **No** — zero-reference not proven |
| Dashboard Today `:8000` / `/mirror/*` | **None** (runtime) |
| Phase 4B | Doc refresh + optional parked-client guidance |

---

## Phase 3C deprecation hardening

| Item | Result |
|------|--------|
| Legacy response headers | `X-OrigenLab-Deprecated-API`, `X-OrigenLab-Replacement: /mirror/*` |
| Legacy startup log warning | **Yes** |
| Mirror API emits deprecation headers | **No** |
| Doc | [API-3_PHASE3C_DEPRECATION.md](./API-3_PHASE3C_DEPRECATION.md) |

---

## Phase 3B live dual-server validation

| Item | Result |
|------|--------|
| Disposable Postgres `:5433` | `origenlab_api3_parity_test` (Docker `origenlab-api3-parity-pg`) |
| `mirror_parity_smoke.py` (12 list routes) | **Passed** — status + top-level JSON keys |
| `npm run smoke:mirror` | **Passed** |
| Orchestration script | `apps/api/scripts/run_mirror_dual_server_parity.sh` |
| Report | [API-3_PHASE3B_LIVE_PARITY_REPORT.md](./API-3_PHASE3B_LIVE_PARITY_REPORT.md) |

---

## Phase 3A consumer cutover (partial)

| Consumer | Change |
|----------|--------|
| `RUNBOOK.md` | Mirror curls on :8001 first; legacy :8000 under deprecated |
| `dashboard_postgres_sync.py` | Post-sync hints prefer :8001 `/mirror/*` |
| `streamlit_api_preview.py` | Default base :8001; `/mirror/*` paths unless base is :8000 |
| `.env.example` | Documents :8001 preferred |
| `npm run smoke:mirror` | `apps/dashboard/scripts/mirror-smoke.mjs` |
| `npm run smoke:legacy` | **Retained** (deprecated :8000) |
| Dashboard Today | **Unchanged** — still operator routes only |

---

## Related documents

| Document | Role |
|----------|------|
| [API-3_PHASE1_MIRROR_ROUTE_DESIGN.md](./API-3_PHASE1_MIRROR_ROUTE_DESIGN.md) | Phase 1 route design + mount order |
| [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md) | Consumer inventory + migration phases |
| [../README.md](../README.md) | Operator API runbook |
