# API-3 Phase 3C — Legacy :8000 deprecation hardening

**Status:** Active (2026-05). Legacy `apps/email-pipeline/src/origenlab_api` **remains**; routes on port **8000** are **not removed** until Phase 6 zero-reference audit.

---

## Operator guidance

| Use case | Preferred | Deprecated |
|----------|-----------|------------|
| Postgres mirror reporting (dashboard KPIs, classification, commercial list, mart contacts/orgs, outbound) | **`apps/api` :8001** — `GET /mirror/*` | **email-pipeline :8000** — same paths without `/mirror` prefix |
| Dashboard v1 Today (warm cases, equipment, contact drilldown) | **`apps/api` :8001** — operator routes only | Do **not** point Vite at :8000 |
| Dual-server parity check | `mirror_parity_smoke.py` + `run_mirror_dual_server_parity.sh` | — |

**Smokes**

- **Preferred:** `cd apps/dashboard && npm run smoke:mirror` (GET `/mirror/*` on :8001)
- **Legacy (compatibility):** `npm run smoke:legacy` (GET `/health`, `/dashboard/summary` on :8000)

---

## Deprecation signals on :8000

Every legacy API HTTP response includes:

| Header | Value |
|--------|--------|
| `X-OrigenLab-Deprecated-API` | `true` |
| `X-OrigenLab-Replacement` | `/mirror/*` |

On startup, uvicorn logs a **warning** with the same guidance. CORS `expose_headers` includes these names for parked React clients.

**Mirror API (:8001)** does **not** set these headers.

---

## Phase 6 gate (do not delete early)

Do **not** remove `apps/email-pipeline/src/origenlab_api` until:

- Streamlit, RUNBOOK, sync hints, and internal scripts default to :8001 `/mirror/*`
- `test_api_*` and parity smokes pass without :8000
- Grep audit shows no runtime dependency on legacy paths

See [API-3_RELOCATION_AUDIT.md](./API-3_RELOCATION_AUDIT.md).

---

## Related

| Document | Role |
|----------|------|
| [API-3_PHASE2_PARITY_CHECKLIST.md](./API-3_PHASE2_PARITY_CHECKLIST.md) | Route matrix |
| [API-3_PHASE3B_LIVE_PARITY_REPORT.md](./API-3_PHASE3B_LIVE_PARITY_REPORT.md) | Live dual-server validation |
| [../../email-pipeline/docs/RUNBOOK.md](../../email-pipeline/docs/RUNBOOK.md) | Operator curls |
