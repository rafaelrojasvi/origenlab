# Streamlit retirement audit

**Date:** 2026-06-02  
**Scope:** `apps/email-pipeline` Streamlit stack vs `apps/api` (:8001) + `apps/dashboard` (React)  
**Rules for this audit:** read-only inventory — **no deletions**, **no runtime behavior changes**

**Operator decision (2026-06-04):** Active UI = `apps/dashboard`; active API = `apps/api`; Streamlit retired from product path. Phased plan: [`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md).

**Verdict (executive, 2026-06-02):** Full removal required **phased** extraction first. **Update (2026-06-04):** Python Streamlit UI **deleted**; `streamlit_draft_helpers.py` **renamed** to `draft_review_helpers.py`. Active UI = dashboard + API. Env-flag `streamlit_*` helpers and `read/*` modules remain. See [`STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md`](STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md).

---

## 1. Inventory — Streamlit entrypoints

### 1.1 Primary app

| Path | LOC (approx.) | Role |
|------|---------------|------|
| `apps/business_mart_app.py` (removed 2026-06-04) | 3,619 | Single Streamlit process: sidebar nav, SQLite RO connection, page router, inline SQL for contacts/orgs/documents/equipment |

**Run locally (historical — pre-2026-06-04 retirement; do not use):**

```bash
# cd apps/email-pipeline
# uv run --group ui streamlit run apps/business_mart_app.py
# LAN (removed): was scripts/tools/run_streamlit_lan.sh — use streamlit --server.address 0.0.0.0
```

### 1.2 `streamlit_*` modules (`src/origenlab_email_pipeline/`)

| Module | LOC | `import streamlit` | Primary responsibility |
|--------|-----|--------------------|-------------------------|
| `streamlit_prioridad_pages.py` | 934 | Yes | Qué hacer hoy, casos para revisar, cola marketing, borrador comercial |
| `streamlit_today_workspace.py` | 383 | No* | Multi-source “today” row gather (used by prioridad pages + Inicio hints) |
| `streamlit_canonical_dashboard_sql.py` | 357 | No | Canonical Gmail counts/samples — **also imported by Postgres sync** |
| `streamlit_leads_browse.py` | 356 | No | Lead/account browse SQL + filters |
| `streamlit_suppliers_browse.py` | 212 | No | Supplier browse SQL + filters |
| `streamlit_api_preview.py` | 219 | Yes | Optional page: GET `apps/api` `/mirror/*` when `ORIGENLAB_API_BASE_URL` set |
| `streamlit_prioridad_copy.py` | 160 | No | Spanish operator copy helpers |
| `streamlit_prioridad_handoffs.py` | 147 | Yes | Session navigation / page redirects |
| `streamlit_page_status.py` | 122 | Yes | KPI + page status presets |
| `streamlit_borrador_support.py` | 115 | No | Marketing variant labels, pilot batch load |
| `tatiana_copilot/streamlit_draft_helpers.py` | 378 | No | Draft package build + `reports/out/*_streamlit_borrador_comercial` export |

\*No top-level `import streamlit` in file; consumed only from Streamlit renderers.

**Total Streamlit-touched Python (app + modules):** ~7,000 LOC.

### 1.3 Docker / compose

| Artifact | Streamlit usage |
|----------|-----------------|
| ~~`Dockerfile`~~ | **Removed** (2026-06-04) — was UI-only Streamlit image |
| ~~`docker-compose.yml`~~ | **Removed** (2026-06-04) — was `business-mart` :8501 |
| [`docker-compose.dashboard-postgres.yml`](../../docker-compose.dashboard-postgres.yml) | Postgres for **mirror** stack — **not** Streamlit |

No monorepo `.github` workflow references Streamlit or 8501 (as of this audit).

### 1.4 Dependency group (`pyproject.toml`)

```toml
[dependency-groups]
ui = [
    "pandas<3",
    "streamlit>=1.36",
    "xlrd>=2.0.1",
]
```

- **`streamlit`** is only pulled via `--group ui` (README, local run; Docker image removed).
- **`pandas`** is also in the `ml` group — removing `ui` does not remove pandas from ML installs.
- **`xlrd`** may still be needed outside Streamlit (spreadsheet ingest); verify before dropping from `ui`.

### 1.5 Docs mentioning Streamlit (non-exhaustive; high-signal)

| Doc | Notes |
|-----|--------|
| [`docs/RUNBOOK.md`](../RUNBOOK.md) | Docker Streamlit section (`#m-eprun-docker-streamlit`), contacto Gmail filter contract, commercial intel UI, `test_business_mart_app_ux.py` |
| [`docs/OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md) | Streamlit = review + sidecar RW; Cola env bypass |
| [`docs/EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md) | Streamlit = supporting SQLite UI (not parked like Postgres) |
| [`docs/pipeline/STREAMLIT_DATA_FRESHNESS.md`](../pipeline/STREAMLIT_DATA_FRESHNESS.md) | **Salud de datos** semantics |
| [`docs/pipeline/BUSINESS_MART.md`](../pipeline/BUSINESS_MART.md), [`MART_FRESHNESS.md`](../pipeline/MART_FRESHNESS.md) | Mart + UI |
| [`docs/pipeline/CASOS_PARA_REVISAR.md`](../pipeline/CASOS_PARA_REVISAR.md), [`COMMERCIAL_INTEL_V1.md`](../pipeline/COMMERCIAL_INTEL_V1.md) | Casos + candidatos |
| [`docs/architecture/POSTGRES_API_DASHBOARD_PLAN.md`](../architecture/POSTGRES_API_DASHBOARD_PLAN.md) | Historical: “do not remove Streamlit” |
| [`README.md`](../../README.md), [`AGENTS.md`](../../AGENTS.md) | Operator stack pointer |
| [`docs/audits/CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md) | Phase 0 planner flags `streamlit_prioridad_pages` |

### 1.6 Tests mentioning Streamlit

| Test file | Focus |
|-----------|--------|
| `test_streamlit_api_preview.py` | API preview URLs, env gating |
| `test_streamlit_canonical_dashboard_sql.py` | SQL helpers |
| `test_streamlit_canonical_operational.py` | Canonical + today workspace |
| `test_streamlit_today_workspace.py` | Today row gather |
| `test_streamlit_prioridad_pages_import.py` | Import smoke |
| `test_streamlit_prioridad_handoffs.py` | Navigation / session |
| `test_streamlit_prioridad_copy.py` | Copy helpers |
| `test_streamlit_navigate_to_page_redirects.py` | Legacy page name redirects |
| `test_streamlit_page_status.py` | Status presets |
| `test_streamlit_borrador_support.py` | Borrador support |
| `test_streamlit_draft_helpers.py` | Tatiana export |
| `test_streamlit_leads_browse.py` | Lead SQL |
| `test_streamlit_suppliers_browse.py` | Supplier SQL |
| `test_business_mart_app_ux.py` | Sidebar pages, commercial section contracts |
| `test_lead_contact_research.py` | `streamlit_leads_review_rw_enabled` |
| `test_contacto_gmail_source_contract.py` | Streamlit/Gmail predicate alignment |
| `test_sqlite_mart_core_to_postgres_migrate.py` | Imports `streamlit_canonical_dashboard_sql` |
| `test_package_import_boundaries.py` | Tatiana must not import `streamlit_*` |

**Approx. test surface:** 13 dedicated `test_streamlit_*` files + UX/integration tests (~30 files touch “streamlit” in grep).

---

## 2. Streamlit navigation map (sidebar)

### Primary sidebar (`PRIMARY_SIDEBAR_PAGES`)

| Streamlit page | Submodule / renderer |
|----------------|----------------------|
| Inicio | `render_inicio_page` + `streamlit_today_workspace` |
| Actividad contacto Gmail | `render_contacto_gmail_activity_page` |
| Clasificación comercial | `render_clasificacion_comercial_page` |
| Seguimientos y casos | `render_cases_to_review_page` (prioridad) |
| Contactos y organizaciones | Inline mart drill-downs (Contactos / Organizaciones / Documentos tabs) |
| Oportunidades | Equipment + signals views |
| Outbound / No repetir | Suppression + outreach surfaces |
| Histórico / Archivo legacy | Legacy source views |
| Salud de datos | `render_data_health_page` |
| Herramientas / Runbook | Inner menu (below) |
| API preview (optional) | `streamlit_api_preview` if `ORIGENLAB_API_BASE_URL` set |

### Herramientas inner menu (`_HERRAMIENTA_INNER_OPTIONS`)

| Tool | Renderer |
|------|----------|
| Runbook (guía operador) | `render_herramientas_runbook_page` |
| Qué hacer hoy | `render_que_hacer_hoy_page` |
| Cola outreach marketing | `render_next_marketing_queue_page` |
| Borrador comercial | `render_commercial_draft_review_page` |
| Leads y cuentas | `render_leads_y_cuentas_page` + `streamlit_leads_browse` |
| Proveedores | `render_proveedores_page` + `streamlit_suppliers_browse` |
| Candidatos comerciales | `commercial_intel_review` (inline in app) |

---

## 3. Gap analysis — API + dashboard vs Streamlit

### 3.1 Active HTTP surfaces

**Operator routes (`apps/api`, SQLite or postgres backend for Today):**

| Route | Dashboard use |
|-------|-----------------|
| `GET /health` | System / Today |
| `GET /operator/status` | Today summary, warnings |
| `GET /cases/warm` | Today, **Inbox** (bandeja) |
| `GET /opportunities/equipment` | Today, **Opportunities** |
| `GET /contacts/{email}` | Contact drilldown (Today + tables) |

**Mirror routes (`GET /mirror/*`, Postgres when `ORIGENLAB_API_BACKEND=postgres`):**

| Prefix | Dashboard use |
|--------|-----------------|
| `/mirror/dashboard/summary` | Streamlit API preview only; partial overlap with Today counts |
| `/mirror/health/dependencies` | API preview |
| `/mirror/outbound/readiness` | API preview; Today mirror note |
| `/mirror/classification/*` | **Legacy** client only (`src/legacy/`) — not active `DashboardApp` |
| `/mirror/commercial/deals` | **Deals** page |
| `/mirror/catalog/products` | **Catálogo** |
| `/mirror/leads/prospects` | **Prospectos** |
| `/mirror/contacts`, `/mirror/organizations` | **Contacts** page (list; not same as `/contacts/{email}`) |
| `/mirror/outbound/suppressions/*` | No first-class dashboard page (read via mirror smoke) |

**Important:** [`apps/dashboard/src/App.tsx`](../../../dashboard/src/App.tsx) mounts full **`DashboardApp`** (11 sections). v1 freeze docs still describe “Today only”; active code has expanded **read-only** sections (Hoy, Bandeja, Oportunidades, Negocios, Prospectos, Catálogo, Proveedores, etc.). Policy tests (`noWritePolicy.test.ts`) still enforce **GET-only** — no write parity in React.

### 3.2 Page-by-page replacement status

| Streamlit page | API / dashboard replacement | Gap |
|----------------|----------------------------|-----|
| **Inicio** | Today summary (`/operator/status`, warm + equipment counts) | Streamlit adds canonical SQL KPIs, outbound readiness on SQLite, today-workspace deep links — **partial** |
| **Actividad contacto Gmail** | `GET /emails/recent` (API exists; **not** wired in active dashboard) | Recent mail table + doc attachments — **dashboard missing** |
| **Clasificación comercial** | `/mirror/classification/*` (legacy dashboard only) | Heuristic buckets + sample grid — **no active React page** |
| **Seguimientos y casos** | Warm cases ≈ `/cases/warm` | `cases_review_queue` + commercial intel hints + handoffs — **partial** (no CI case detail API) |
| **Contactos y organizaciones** | `/mirror/contacts`, `/mirror/organizations` + `/contacts/{email}` | Streamlit mart drill-down, copy buttons, **suppression RW** — **read partial, write none** |
| **Oportunidades** | `/opportunities/equipment` + mirror commercial | Equipment table yes; opportunity_signals explorer — **partial** |
| **Outbound / No repetir** | `/mirror/outbound/*` (mirror) | Streamlit shows SQLite suppressions + state; mirror lists — **read partial**; **RW only Streamlit+CLI** |
| **Histórico / Archivo legacy** | None | Archive scope views — **missing** |
| **Salud de datos** | None | Mart vs raw freshness, `pipeline_kv` — **missing** (see `STREAMLIT_DATA_FRESHNESS.md`) |
| **Herramientas → Qué hacer hoy** | Today summary cards | Multi-source workspace table — **missing** |
| **Cola outreach marketing** | `export_next_marketing_recipients.py` CLI | Interactive queue + preflight UI — **CLI only** |
| **Borrador comercial** | Tatiana scripts / dataset tools | Draft + export to `reports/out` — **Streamlit only** |
| **Leads y cuentas** | `/mirror/leads/prospects` | Browse filters + **`lead_contact_research` RW** — **read partial, write Streamlit** |
| **Proveedores** | Suppliers page (mirror) | Browse parity improving — verify filter parity |
| **Candidatos comerciales** | None in API | `commercial_intel_review` + **`ORIGENLAB_STREAMLIT_COMMERCIAL_REVIEW_RW`** — **missing** |
| **API preview** | N/A (meta) | Becomes redundant when dashboard uses mirror — **remove last** |

### 3.3 Write / sidecar features (blockers for deletion)

Streamlit opt-in writes (all require **writable** SQLite + env flag):

| Feature | Env flag | CLI / module alternative |
|---------|----------|---------------------------|
| Contact email suppression | `ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW=1` | `add_manual_contact_suppressions.py`, NDR tools, `import_operator_outreach_blocklist.py` |
| Lead contact research | `ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW=1` | `import_lead_contact_research_csv.py` |
| Commercial candidate review | `ORIGENLAB_STREAMLIT_COMMERCIAL_REVIEW_RW=1` | `commercial_intel_review` module + builder scripts |
| Borrador export | writable `ORIGENLAB_REPORTS_DIR` | Tatiana export helpers (filesystem) |
| Marketing cola | — (read-only queue) | `export_next_marketing_recipients.py` |
| Sent preflight bypass | `ORIGENLAB_STREAMLIT_ALLOW_EMPTY_SENT_HISTORY=1` | CLI `--allow-empty-sent-history` (audited) |

**Dashboard/API policy:** `apps/api` is **GET-only** by design (`test_no_write_policy.py`). Retiring Streamlit **without** new audited write APIs means operators must use **CLIs** for all sidecar mutations.

---

## 4. Logic trapped in Streamlit UI — migrate to `src/` read services

Priority extractions (behavior-preserving renames; tests move with modules):

| Current module | Suggested `src/` home | Non-Streamlit consumers today |
|----------------|----------------------|------------------------------|
| `streamlit_canonical_dashboard_sql.py` | `canonical_operational_sql.py` or `read/canonical_gmail_stats.py` | **`classification_postgres_mirror.py`**, migrate tests |
| `streamlit_leads_browse.py` | `read/leads_browse.py` | — |
| `streamlit_suppliers_browse.py` | `read/suppliers_browse.py` | — |
| `streamlit_today_workspace.py` | `read/today_workspace.py` | Could back future `GET /operator/today-workspace` |
| `streamlit_borrador_support.py` | `marketing_pilot_batch.py` (no `streamlit_` prefix) | `streamlit_prioridad_pages`, tests |
| `streamlit_prioridad_copy.py` | `operator_copy_es.py` | Pure copy — safe move |
| `streamlit_page_status.py` | Split: `operator_page_status.py` (data) + keep thin Streamlit renderer OR delete with UI | Tests on presets only |
| `load_contacto_gmail_*` in `business_mart_app.py` | `read/contacto_gmail_activity.py` | Align with `contacto_gmail_source` contract tests |
| `render_data_health_page` SQL | `read/data_health.py` | Future API `GET /operator/data-health` |
| `streamlit_api_preview.py` | Delete after dashboard parity — logic is urllib GET | — |
| `tatiana_copilot/streamlit_draft_helpers.py` | `tatiana_copilot/draft_export.py` | Remove `streamlit_` name; keep Tatiana boundary rules |

**Do not delete `streamlit_prioridad_pages.py` until:** marketing queue UI, borrador export, and casos queue have CLI or API+React replacements with tests.

---

## 5. Dependencies removable later

| Dependency / artifact | When safe to remove |
|----------------------|---------------------|
| `streamlit>=1.36` (`ui` group) | After app + all `import streamlit` renderers removed |
| ~~`Dockerfile`~~ + ~~`docker-compose.yml`~~ | **Removed** (2026-06-04) |
| ~~`scripts/tools/run_streamlit_lan.sh`~~ | **Removed** (2026-06-04) |
| `apps/business_mart_app.py` | Last — after all pages migrated |
| `streamlit_*` modules | Per-module after extraction + zero imports |
| `ui` group `xlrd` | Only if no other script needs it via `ui` |
| Env vars `ORIGENLAB_STREAMLIT_*` | After RW UX exists elsewhere |

**Keep (not Streamlit-specific):** `pandas`, `cases_review_queue`, `next_marketing_queue`, `commercial_intel_*`, Tatiana copilot core.

---

## 6. Docs and tests to change before deletion

### Docs (minimum set)

1. [`RUNBOOK.md`](../RUNBOOK.md) — remove/replace `#m-eprun-docker-streamlit`, Streamlit-first troubleshooting, redirect to dashboard + CLIs  
2. [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md) — drop Streamlit Cola env bypass section or map to CLI-only  
3. [`EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md) — clarify single operator UI = React  
4. [`README.md`](../../README.md) — ~~drop `uv run --group ui streamlit run apps/business_mart_app.py` primary path~~ **done** (2026-06-04); that launch command is historical only — **do not use**
5. [`STREAMLIT_DATA_FRESHNESS.md`](../pipeline/STREAMLIT_DATA_FRESHNESS.md) — **migrate** to `DATA_HEALTH.md` (UI-agnostic)  
6. [`COMMERCIAL_INTEL_V1.md`](../pipeline/COMMERCIAL_INTEL_V1.md), [`CASOS_PARA_REVISAR.md`](../pipeline/CASOS_PARA_REVISAR.md) — operator paths via dashboard/API/CLI  
7. Root [`AGENTS.md`](../../../../AGENTS.md) — operator stack table  
8. [`apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](../../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md) — reconcile “Today only” with multi-section `DashboardApp`  

### Tests

| Action | Tests |
|--------|-------|
| Rename/move with extracted modules | `test_streamlit_canonical_*` → `test_canonical_operational_sql.py`, etc. |
| Delete last | `test_streamlit_prioridad_pages_import.py`, handoffs tests that need `st.session_state` |
| Keep behavior | `test_contacto_gmail_source_contract.py`, `test_business_mart_app_ux.py` → rewrite against read modules or drop when app deleted |
| API/dashboard | Add parity tests for each retired page (warm cases already have API tests) |

---

## 7. Operator workflows still depending on Streamlit

| Workflow | Still needs Streamlit? | Alternative today |
|----------|------------------------|-------------------|
| Daily send / DNR / ingest | **No** | `operator_status.py`, RUNBOOK CLIs |
| Warm case triage (read) | **Optional** | Dashboard **Hoy** + **Bandeja** |
| Equipment opportunities (read) | **Optional** | Dashboard **Oportunidades** / Today |
| Postgres mirror preview | **Optional** | Dashboard mirror sections + `mirror-smoke.mjs` |
| Mart / ingest freshness audit | **Yes** | **Salud de datos** only in Streamlit |
| Marketing recipient queue preview | **Yes** | CLI export only (no interactive UI elsewhere) |
| Tatiana borrador + export package | **Yes** | Streamlit + `streamlit_draft_helpers` |
| Manual suppression / lead research / CI review | **Yes** (RW) | CLIs + CSV imports (heavier than forms) |
| Contact/org/document mart browse | **Partial** | Dashboard contacts/deals; less depth than Streamlit |
| LAN/WSL operator laptop UI | **Often** | Docker Streamlit :8501 documented in RUNBOOK |

**Conclusion:** Production **send safety** does not require Streamlit. **Human review loops** (marketing queue, borrador, data health, sidecar edits) still do.

---

## 8. Keep / migrate / remove table

| Asset | Action | Notes |
|-------|--------|-------|
| `apps/business_mart_app.py` | **Remove (late)** | After all pages have replacements |
| `streamlit_prioridad_pages.py` | **Migrate then remove** | Largest UX; borrador + cola |
| `streamlit_canonical_dashboard_sql.py` | **Migrate first** | Blocking: `classification_postgres_mirror` |
| `streamlit_leads_browse.py` | **Migrate** | → `read/leads_browse.py` |
| `streamlit_suppliers_browse.py` | **Migrate** | → `read/suppliers_browse.py` |
| `streamlit_today_workspace.py` | **Migrate** | Optional API endpoint |
| `streamlit_api_preview.py` | **Remove (early)** | Subsumed by dashboard mirror |
| `streamlit_page_status.py` | **Remove with UI** | Streamlit-only rendering |
| `streamlit_prioridad_handoffs.py` | **Remove with UI** | Session state |
| `streamlit_prioridad_copy.py` | **Migrate** | Pure copy |
| `streamlit_borrador_support.py` | **Migrate** | Shared with borrador |
| `streamlit_draft_helpers.py` | **Migrate** | Rename; keep Tatiana boundary |
| ~~`Dockerfile`~~ / ~~`docker-compose.yml`~~ | **Removed** (2026-06-04) |
| `pyproject.toml` `ui` group | **Remove (late)** | After streamlit dep gone |
| `contact_email_suppression.streamlit_*_enabled` | **Migrate** | Generic `operator_rw_enabled` or drop flags |
| `RUNBOOK` Streamlit sections | **Migrate docs** | Point to dashboard + CLIs |

---

## 9. API/dashboard replacement matrix (target end state)

| Streamlit page | Target replacement |
|----------------|-------------------|
| Inicio | `GET /operator/status` + Today summary UI; optional `GET /operator/canonical-kpis` |
| Actividad contacto Gmail | `GET /emails/recent` + new dashboard **Actividad** or expand Inbox |
| Clasificación comercial | `GET /mirror/classification/*` + dashboard page (revive patterns from `src/legacy/`) |
| Seguimientos y casos | `GET /cases/warm` + `GET /cases/review` (new) backed by `cases_review_queue` |
| Contactos y organizaciones | `/mirror/contacts`, `/mirror/organizations`, `/contacts/{email}` |
| Oportunidades | `/opportunities/equipment` + mirror commercial signals |
| Outbound / No repetir | `/mirror/outbound/*` + documented CLIs for writes |
| Histórico / Archivo legacy | `GET /mirror/...?scope=archive` (extend mirror) |
| Salud de datos | `GET /operator/data-health` (new, SQLite-only metrics) |
| Qué hacer hoy | `GET /operator/today-workspace` from extracted `today_workspace` |
| Cola outreach marketing | CLI + optional read-only `GET /operator/marketing-queue` |
| Borrador comercial | Tatiana CLI + export; optional read-only draft preview API |
| Leads y cuentas | `/mirror/leads/*` + CLI/CSV for research writes |
| Proveedores | `/mirror/...` suppliers + dashboard **Proveedores** |
| Candidatos comerciales | `GET /mirror/commercial/candidates` + audited write API or CLI-only |
| API preview | **Remove** — dashboard is the preview |

---

## 10. Tests required before deletion

| Gate | Command / test |
|------|----------------|
| Extracted SQL parity | `uv run pytest tests/test_streamlit_canonical_dashboard_sql.py` (renamed), `test_sqlite_mart_core_to_postgres_migrate.py` |
| Gmail contacto contract | `tests/test_contacto_gmail_source_contract.py` |
| Marketing queue logic | `tests/test_next_marketing_queue.py` (existing) + API smoke if endpoint added |
| Outbound preflight | `tests/test_outbound_sent_preflight.py` — no Streamlit-only bypass without doc |
| Lead browse | `tests/test_streamlit_leads_browse.py` → read module path |
| Commercial intel | `tests/test_commercial_intel_*.py` |
| Dashboard read-only | `cd apps/dashboard && npm test` |
| API GET-only | `cd apps/api && uv run pytest tests/test_no_write_policy.py` |
| No orphan imports | `rg 'streamlit_' src/` and `rg 'import streamlit'` clean |
| UX regression (until app removed) | `tests/test_business_mart_app_ux.py` |

---

## 11. Suggested PR sequence

| Phase | PR | Risk | Deliverable |
|-------|-----|------|-------------|
| **S0** | This audit only | None | `STREAMLIT_RETIREMENT_AUDIT_20260602.md` |
| **S1** | Extract `streamlit_canonical_dashboard_sql` → neutral module | Low | `classification_postgres_mirror` unchanged behavior; tests renamed |
| **S2** | Extract `streamlit_leads_browse`, `streamlit_suppliers_browse`, `streamlit_today_workspace`, `streamlit_borrador_support`, `streamlit_prioridad_copy` | Low | Streamlit imports new paths; deprecate old names (re-export shim) |
| **S3** | API: `GET /operator/data-health`, `GET /emails/recent` wired in dashboard | Medium | Parity for Salud de datos + Actividad |
| **S4** | API: `GET /cases/review` or mirror commercial candidates (read) | Medium | Casos + Candidatos read paths |
| **S5** | Dashboard pages: classification, data health, marketing queue (read-only) | Medium | Operator read parity |
| **S6** | Docs: RUNBOOK redirect, deprecate Docker Streamlit | Low | Operators informed |
| **S7** | Remove `streamlit_api_preview` + env `ORIGENLAB_API_BASE_URL` preview | Low | |
| **S8** | Sidecar writes: expand CLIs **or** new audited POST API (explicit approval) | High | Replace `ORIGENLAB_STREAMLIT_*_RW` |
| **S9** | Borrador: CLI-only Tatiana export; drop Streamlit borrador page | Medium–High | |
| **S10** | Remove `business_mart_app.py`, `streamlit_*`, `ui` group, Dockerfile | High | Final deletion PR |

**Do not start S10 until:** S1–S5 read parity signed off by operators; S8 write path agreed (CLIs-only is acceptable if documented).

---

## 12. Related artifacts

- [`CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md) — Phase 0 planner  
- [`POSTGRES_API_PIPELINE_MESS_AUDIT.md`](POSTGRES_API_PIPELINE_MESS_AUDIT.md) — API/Streamlit overlap history  
- [`apps/api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md`](../../../api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md) — :8000 removed; mirror on :8001  
- [`apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](../../../dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md) — active operator UI handoff  

---

## 13. Audit handoff

| Item | Value |
|------|--------|
| **Files created** | `docs/audits/STREAMLIT_RETIREMENT_AUDIT_20260602.md` |
| **Code/tests changed** | None (audit only) |
| **Commands run** | `wc -l` on Streamlit modules; repo `rg` / glob inventory |
| **Recommendation** | **Defer deletion**; start **S1–S2 extractions** and **S3–S5 read parity** before any Streamlit removal |
