# Active stack and Streamlit retirement plan — 2026-06-04

Status: canonical (operator stack alignment)  
Owner: email-pipeline-maintainers  
Supersedes nothing — complements [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md)

---

## Active stack

| Layer | Path | Role |
|-------|------|------|
| **Operator UI** | [`apps/dashboard`](../../../dashboard/README.md) | React operator dashboard (**:5173**). Read-only; **GET-only** to API. |
| **Backend / read API** | [`apps/api`](../../../api/README.md) | FastAPI on **:8001** — operator routes + **`GET /mirror/*`** Postgres mirror reporting. |
| **Dashboard read model** | Postgres mirror (sync via `uv run origenlab mirror-dashboard`) | Populated from SQLite by [`scripts/sync/sync_dashboard_postgres_mirror.py`](../../scripts/sync/sync_dashboard_postgres_mirror.py). **Not** send/outbound truth. |
| **Operational truth** | `apps/email-pipeline` SQLite + Gmail Sent ingest | Ingest, mart, commercial intel, outbound safety, DNR, equipment-first queues, QA reports. **No UI** in this package. |

**Daily operator path (2026-06-04):**

1. `cd apps/email-pipeline` → `uv run origenlab status` / safety / digest CLIs on SQLite.  
2. Optional mirror refresh → `uv run origenlab mirror-dashboard` (dry-run default; `--apply` only with approval).  
3. `cd apps/api` → API **:8001**.  
4. `cd apps/dashboard` → React UI **:5173** polling `apps/api`.

See monorepo [`docs/PROJECT_CONTEXT.md`](../../../../docs/PROJECT_CONTEXT.md), root [`AGENTS.md`](../../../../AGENTS.md), and [`docs/RUNBOOK.md`](../RUNBOOK.md#m-eprun-dashboard-optional).

---

## Legacy / parked stack (Streamlit)

**Product decision:** Streamlit is **not** the operator UI anymore. Do **not** add Streamlit features. Do **not** treat Streamlit as source of truth for sends, DNR, or mirror state.

| Artifact | Path / note |
|----------|-------------|
| Streamlit app | [`apps/business_mart_app.py`](../../apps/business_mart_app.py) (~3.6k LOC) |
| Streamlit renderers | `streamlit_prioridad_pages.py`, `streamlit_prioridad_handoffs.py`, `streamlit_page_status.py` |
| Tatiana Streamlit export | `tatiana_copilot/streamlit_draft_helpers.py` |
| Neutral read helpers (already extracted) | `read/today_workspace.py`, `read/leads_browse.py`, `read/suppliers_browse.py` — **keep**; used by API/library paths |
| LAN launcher | [`scripts/tools/run_streamlit_lan.sh`](../../scripts/tools/run_streamlit_lan.sh) |
| Docker UI image | [`Dockerfile`](../../Dockerfile), [`docker-compose.yml`](../../docker-compose.yml) (port **8501**) |
| Dependency group | `pyproject.toml` → `[dependency-groups] ui` (`streamlit`, `pandas`, `xlrd`) |
| Streamlit-focused tests | `tests/test_streamlit_*.py`, `tests/test_business_mart_app_ux.py`, `tests/test_business_mart_internal_domains.py` |
| Streamlit operator docs | `docs/pipeline/STREAMLIT_DATA_FRESHNESS.md`, sections in `RUNBOOK.md` (`#m-eprun-docker-streamlit`), README Streamlit blocks |

**Already removed (Phase 5E–5G):** `streamlit_leads_browse`, `streamlit_suppliers_browse`, `streamlit_today_workspace`, `streamlit_borrador_support`, `streamlit_prioridad_copy`, `streamlit_api_preview`, `streamlit_canonical_dashboard_sql` — logic lives under `read/` or `canonical_operational_sql.py`. See [`tests/test_read_module_shim_parity.py`](../../tests/test_read_module_shim_parity.py).

---

## Decision

- **Active UI:** `apps/dashboard` (React).  
- **Active read API:** `apps/api` + Postgres mirror.  
- **email-pipeline:** batch jobs, CLIs (`origenlab`), SQLite truth, reports — **not** a UI package.  
- **Streamlit:** legacy/parked review surface on SQLite; retirement in phases below.  
- **Prefer:** API/dashboard parity, `origenlab` CLIs, and CSV/JSON under `reports/out/` over new Streamlit pages.

---

## Retirement phases

| Phase | Goal | This PR |
|-------|------|---------|
| **0** | Mark legacy/parked; document active stack | **Yes** — this doc + surgical README/RUNBOOK/APP_CONTEXT/AGENTS notes |
| **1** | Remove Streamlit as *primary* path in top-level docs | **Partial** — README/RUNBOOK pointers; full RUNBOOK dedup deferred |
| **2** | API/dashboard parity checklist per Streamlit page | Documented below — implementation in follow-up PRs |
| **3** | Move remaining Streamlit-only files to `legacy/` or archive | **No** — no file moves/deletes |
| **4** | Drop `ui` group, Docker Streamlit service, LAN script | **No** — after zero references + CI update |

---

## Phase 2 — parity checklist (API + dashboard)

Use before deleting Streamlit pages. Status from [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md) §3.2 (2026-06-04).

| Streamlit capability | Replacement target | Parity |
|---------------------|-------------------|--------|
| Inicio / KPIs | `GET /operator/status`, Today dashboard | Partial |
| Actividad contacto Gmail | `GET /emails/recent` (API) | Dashboard wiring TBD |
| Casos para revisar | `GET /cases/*`, `cases_review_queue` | Partial |
| Contacts / orgs browse | `GET /mirror/contacts`, `/mirror/organizations` | Read partial; RW only CLI/Streamlit |
| Equipment / opportunities | `/opportunities/equipment`, mirror commercial | Partial |
| Outbound / suppressions | `/mirror/outbound/*` + SQLite CLIs | Read partial |
| Salud de datos | — | **Missing** in React |
| Cola outreach marketing | `export_next_marketing_recipients.py` | CLI only |
| Borrador comercial | Tatiana scripts / `streamlit_draft_helpers` | Streamlit-only export |
| Candidatos comerciales | — | **Missing** (RW was Streamlit-only) |
| Sidecar writes (suppression, lead research, commercial review) | CLIs + env-gated Streamlit | **API is GET-only** — CLIs remain truth for writes |

**Write policy:** Retiring Streamlit without new audited write APIs means **all sidecar mutations stay on CLIs** (`refresh-safety`, suppression imports, commercial intel scripts). See [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md).

---

## Candidate files — remove now / later / needs parity

| Category | Path | Remove now? | Notes |
|----------|------|-------------|-------|
| App | `apps/business_mart_app.py` | **Later** | Last — after page parity + write paths documented |
| UI modules | `streamlit_prioridad_pages.py`, `streamlit_prioridad_handoffs.py`, `streamlit_page_status.py` | **Later** | Still imported by app |
| Tatiana UI | `tatiana_copilot/streamlit_draft_helpers.py` | **Later** | Borrador export; rename to non-streamlit name first |
| Read helpers | `read/today_workspace.py`, `read/leads_browse.py`, `read/suppliers_browse.py` | **Keep** | Not Streamlit-only; API/library |
| Docker | `Dockerfile`, `docker-compose.yml` | **Later** | After no deploy dependency |
| Script | `scripts/tools/run_streamlit_lan.sh` | **Later** | With Docker |
| Deps | `pyproject.toml` `ui` group | **Later** | CI still syncs `--group ui` for tests |
| Tests | `tests/test_streamlit_*.py`, `test_business_mart_app_*` | **Later** | Rename/move with modules; keep green CI until Phase 4 |
| Docs | `STREAMLIT_DATA_FRESHNESS.md`, RUNBOOK docker section | **Later** | Migrate to UI-agnostic `DATA_HEALTH.md` |
| Already gone | `streamlit_*_browse`, `streamlit_api_preview`, `streamlit_canonical_dashboard_sql` | **Done** | Phase 5E–5G |

**Do not delete** based on low fan-in alone — `business_mart_app.py` is still a manual entrypoint for some operators until parity is explicit.

---

## What stays in email-pipeline (not retirement targets)

- `uv run origenlab` operator CLI ([`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md))  
- Ingest / mart / commercial / safety scripts ([`SCRIPT_MAP.md`](../SCRIPT_MAP.md))  
- SQLite schema modules, outbound gate, equipment-first builders  
- Postgres **sync** scripts (parked for daily ops but required for dashboard mirror)  
- Shared utilities — [`SHARED_UTILITY_CONTRACTS.md`](../SHARED_UTILITY_CONTRACTS.md)  
- Root/core facade layout — [`MODULE_FACADE_AUDIT_20260604.md`](MODULE_FACADE_AUDIT_20260604.md), [`ROOT_MISC_MODULE_CLASSIFICATION_20260604.md`](ROOT_MISC_MODULE_CLASSIFICATION_20260604.md)

---

## Non-goals (this initiative)

- **No** deletion of Streamlit Python files in Phase 0–1 PRs.  
- **No** runtime behavior changes (Gmail, Postgres sync, send, purge, mirror, `--apply`).  
- **No** import migrations or `core/` facade churn for Streamlit retirement.  
- **No** generic developer-doc expansion unrelated to retirement (prefer this plan + parity checklist).  
- **No** removing `--group ui` from CI until Streamlit tests are retired or rewritten.

---

## Launch surfaces (detail)

See [`STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md`](STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md) — per-path grep evidence, active/legacy, and PR 1 vs PR 3+ delete list.

## Follow-up PR ideas (ordered)

1. **docs:** RUNBOOK — demote `#m-eprun-docker-streamlit` to “legacy”; dashboard section first in operator map. **(PR 1 — done in launch-surface batch)**
2. **docs:** `EXPERIMENTAL_PARKED.md` — Streamlit row → legacy/parked; React = active UI.  
3. **api/dashboard:** Wire `GET /emails/recent`, expand cases/contacts parity (read-only).  
4. **extract:** `streamlit_draft_helpers` → `tatiana_copilot/draft_export.py` (no `streamlit_` prefix).  
5. **ci:** Optional job without `--group ui` once Streamlit tests removed.  
6. **delete:** `business_mart_app.py` + `ui` group — only after parity sign-off.

---

## Verification

```bash
cd apps/email-pipeline
uv run pytest tests/test_active_stack_docs.py tests/test_module_facade_audit.py tests/test_operator_cli.py -q
uv run origenlab audit-facades -- --fail-on-manual-review
```

---

## References

- [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md) — inventory + parity detail  
- [`apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](../../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md)  
- [`apps/api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md`](../../../api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md)
