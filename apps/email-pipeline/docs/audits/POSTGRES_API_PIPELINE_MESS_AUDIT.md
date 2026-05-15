# OrigenLab monorepo audit — Postgres, API, pipeline sprawl

**Status:** generated audit (read-only inspection)  
**Date:** 2026-05-14  
**Scope:** repository `rafaelRojasVi/origenlab` (local path `/home/rafael/dev/freelance/origenlab`)  
**Rules followed:** no deletes, no refactors, no production behavior changes; claims cite paths or command output.

---

## 1. Executive summary

The monorepo is **intentionally two-headed**: a **static Astro marketing site** (`apps/web`) and a **Python email intelligence + human-in-the-loop outreach operations** stack (`apps/email-pipeline`). The email pipeline’s **operational source of truth is SQLite** plus **Gmail Workspace ingest** into the `emails` table; documentation and code agree on this (`apps/email-pipeline/docs/SCRIPT_MAP.md`, `apps/email-pipeline/alembic/env.py`, `apps/email-pipeline/pyproject.toml`).

**PostgreSQL** is **real but partial**: Alembic migrations and **optional** SQLite→Postgres loaders exist under `apps/email-pipeline/alembic/` and `apps/email-pipeline/scripts/migrate/`. **Optional** runtime writes to Postgres exist only when operators pass **`--write-postgres-audit`** on specific outbound scripts (`apps/email-pipeline/src/origenlab_email_pipeline/postgres_outbound_audit.py`, wired from `scripts/leads/export_next_marketing_recipients.py` and `scripts/leads/build_archive_send_batch.py`). There is **no** evidence of the main gate, Streamlit, or daily reads running against Postgres.

**REST/API product backend:** **not found** (no FastAPI, Flask, Starlette app, or API router usage in Python). There is a **local-only** `http.server`-based CSV file server for lead CSVs (`apps/email-pipeline/scripts/leads/advanced/run_contact_hunt_web_server.py`), which is **not** a general API.

**Test health signal:** `uv run pytest -q` in `apps/email-pipeline` completed with **1024 passed, 7 skipped, 4 failed** (failures in `tests/test_outreach_ingest_sync.py` and Streamlit label tests). This indicates **some drift** between tests and current UI strings / ingest behavior; the suite is large and mostly green.

**Recommended strategic bias:** **stabilize SQLite + documented daily lanes first** (already canonical in `SCRIPT_MAP.md` / `RUNBOOK.md`), treat Postgres as **parallel archive + optional audit** until you explicitly want app reads on Postgres.

---

## 2. Current reality check

| Area | Purpose | Maturity | Role vs “core” |
|------|---------|----------|----------------|
| `apps/web` | Public marketing (Astro, TS) | **Production-oriented** (build artifacts present in workspace snapshot) | **Core** for public web; **independent** of email DB |
| `apps/email-pipeline` | Ingest, mart, leads, outbound safety, reports, Streamlit operator UI | **Mature but wide** — strong docs + large test suite + many scripts | **Core** of commercial ops tooling |
| `apps/email-pipeline/src/origenlab_email_pipeline/` | Shared library (gates, schemas, Streamlit modules, etc.) | **Core** — primary place for behavior | **Core** |
| `apps/email-pipeline/scripts/` | CLI entrypoints | **Large surface** (~134 `.py` files under `scripts/` per `find`) | **Ops + lab + migration** mix |
| `apps/email-pipeline/docs/` | Canonical operator + architecture docs | **Strong** — explicit “truth hierarchy” in `docs/README.md` | **Core** (navigation) |
| `docs/` (repo root) | Monorepo context, business rules | **Canonical** (`docs/PROJECT_CONTEXT.md`) | **Core** |
| `apps/email-pipeline/alembic/` | Postgres DDL migrations | **Implemented** (5 version files + `env.py`) | **Support / future** — not SQLite runtime |
| `apps/email-pipeline/docker-compose.yml` | Container for Streamlit | **Implemented** — binds host data read-only | **Support** |
| Tests `apps/email-pipeline/tests/` | Regression + contracts | **Extensive** — 1000+ tests; **4 failures observed** | **Core** quality signal |

---

## 3. PostgreSQL status

**Classification: `PARTIAL_IMPLEMENTATION`**

Rationale: **schemas and migration tooling are implemented**; **data loaders and optional audit are implemented**; the **primary application path remains SQLite** for OLTP-style operations and Streamlit (`apps/email-pipeline/docs/SCRIPT_MAP.md` states Postgres is optional and not primary OLTP). Postgres is therefore **not** `PRODUCTION_USED` as the system-wide database, and **not** `DOCS_ONLY` because code and Alembic revisions exist.

### 3.1 Evidence — what exists

| Kind | Paths |
|------|--------|
| Alembic env (Postgres-only URL) | `apps/email-pipeline/alembic/env.py` |
| Alembic revisions | `apps/email-pipeline/alembic/versions/20260419_0001_initial_schemas_and_ops.py` … `0005_outbound_export_audit_tables.py` |
| SQLite → Postgres loaders | `apps/email-pipeline/scripts/migrate/sqlite_archive_to_postgres.py`, `sqlite_document_master_to_postgres.py`, `sqlite_outbound_sidecars_to_postgres.py` |
| Pre-migrate validator | `apps/email-pipeline/scripts/qa/validate_sqlite_archive_for_postgres.py` |
| Optional runtime audit (psycopg) | `apps/email-pipeline/src/origenlab_email_pipeline/postgres_outbound_audit.py` |
| CLI flags using audit | `apps/email-pipeline/scripts/leads/export_next_marketing_recipients.py`, `apps/email-pipeline/scripts/leads/build_archive_send_batch.py` (per grep; `--write-postgres-audit`) |
| Dependencies | `apps/email-pipeline/pyproject.toml` dependency group `postgres` (Alembic, SQLAlchemy, psycopg) |
| Design docs | `apps/email-pipeline/docs/pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md`, `apps/email-pipeline/docs/pipeline/POSTGRES_SCHEMA_TARGET_V1.md` (referenced from `SCRIPT_MAP.md`) |
| Tests (no live DB required for many) | `apps/email-pipeline/tests/test_alembic_initial_migration.py`, `test_sqlite_archive_to_postgres_migrate.py`, `test_sqlite_document_master_to_postgres_migrate.py`, `test_sqlite_outbound_sidecars_to_postgres_migrate.py`, `test_validate_sqlite_archive_for_postgres.py`, `test_postgres_outbound_audit.py` |

### 3.2 What is actively used at runtime?

- **Default daily workflow:** **SQLite** + files under `reports/out/active/current/` (documented in `SCRIPT_MAP.md`).
- **Postgres:** used when an operator **runs Alembic**, **runs migrate scripts against a URL**, or passes **`--write-postgres-audit`** on the two outbound export scripts. Streamlit app `apps/email-pipeline/apps/business_mart_app.py` imports `sqlite3` and pipeline modules — **no Postgres driver usage in the portion inspected** (opening lines show SQLite).

### 3.3 What is complete vs missing vs risky

| | Detail |
|---|--------|
| **Complete** | Alembic scaffolding; archive migration script with validation hooks; docs describing load order and safety; unit tests around migrate helpers and audit module; optional audit wiring behind explicit flags. |
| **Doc clarity (2026-05-14)** | **`.env.example`**, [`RUNBOOK.md`](../RUNBOOK.md#m-eprun-postgres-optional), and [`SCRIPT_MAP.md`](../SCRIPT_MAP.md) now document optional `ALEMBIC_DATABASE_URL` / `ORIGENLAB_POSTGRES_URL`, the **different** URL resolution order for **Alembic** vs **migrate scripts / `--write-postgres-audit`**, and a **scratch Postgres first** warning for loaders. |
| **Risky** | Migrate scripts are **break-glass** (truncate/load semantics documented in `POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md` and `SCRIPT_MAP.md`). Running against wrong URL is high blast radius. **Dual stores** (SQLite truth + Postgres copy) can **diverge** if procedures are not disciplined. |

### 3.4 Commands that would prove Postgres works

1. **Install extras:** `cd apps/email-pipeline && uv sync --group postgres` (from `pyproject.toml` / `REPRODUCIBILITY.md`).
2. **Set URL:** `export ALEMBIC_DATABASE_URL='postgresql+psycopg://…'` (see `alembic/env.py`).
3. **Upgrade:** `uv run alembic -c alembic.ini upgrade head` (standard Alembic; ini path per repo convention — confirm with `apps/email-pipeline/README.md` or `RUNBOOK.md`).
4. **Validate SQLite corpus:** `uv run python scripts/qa/validate_sqlite_archive_for_postgres.py --strict` (requires real SQLite path).
5. **Load archive:** `uv run python scripts/migrate/sqlite_archive_to_postgres.py --help` then a **non-production** dry run / small DB trial per script docs (script implements connectivity and batch load; see file header in `sqlite_archive_to_postgres.py`).
6. **Optional audit:** run export scripts with `--write-postgres-audit` only after schema at least includes outbound audit tables (`RUNBOOK.md` section on optional Postgres outbound audit).

Optional pytest marker mentioned in `tests/test_alembic_initial_migration.py` for live upgrade smoke (`ALEMBIC_DATABASE_URL`).

### 3.5 Minimum next step if continuing Postgres migration

1. **Prove Alembic head** on a disposable Postgres instance (empty DB → upgrade head).
2. **Run** `validate_sqlite_archive_for_postgres.py --strict` on production SQLite **before** first load.
3. **Pilot load** `sqlite_archive_to_postgres.py` on a **copy** of SQLite + scratch Postgres; compare counts (script emits JSON summary fields per implementation).

*(Env template lines for Postgres URLs are in `.env.example` and the operator table is in `RUNBOOK.md` § Optional PostgreSQL — 2026-05-14.)*

### 3.6 Postgres now vs stabilize SQLite first?

**Recommendation:** **stabilize SQLite + daily lanes + tests first**, unless you have a concrete need for **centralized reporting on Postgres** or **multi-writer** access. The repo already encodes this priority in `SCRIPT_MAP.md` / `QUALITY_AND_REFACTOR_STRATEGY.md`. Postgres remains valuable as **archive durability** and **optional audit**, not as an urgent cutover.

---

## 4. API status

**Classification: `NOT_FOUND`** (for a product REST/GraphQL backend)

### 4.1 What was searched

- Ripgrep for `FastAPI`, `Flask`, `APIRouter`, `@router`, `uvicorn`, `starlette` across `*.py` / config: **no matches** in the workspace snapshot used for this audit.

### 4.2 Related network surfaces (not “the API”)

| Item | Path | Nature |
|------|------|--------|
| **Streamlit** | `apps/email-pipeline/apps/business_mart_app.py` (+ modules under `src/origenlab_email_pipeline/streamlit_*.py`) | **Operator UI** — not a public REST API |
| **Local CSV HTTP server** | `apps/email-pipeline/scripts/leads/advanced/run_contact_hunt_web_server.py` | `http.server` + Basic Auth; serves `leads_*.csv` from `reports/out/` — **local / ad hoc** |
| **Gmail send script** | `apps/email-pipeline/scripts/qa/send_inline_html_email_via_gmail_api.py` | **Break-glass** client to Gmail; not a served API |
| **Docker** | `apps/email-pipeline/docker-compose.yml` | Exposes **port 8501** for Streamlit only |

### 4.3 Answers

| Question | Answer |
|----------|--------|
| Does an actual API exist? | **No** general backend API. |
| Where exactly is it? | **N/A** for REST. Near-API utilities above are script-local. |
| What does it expose? | **N/A** (Streamlit exposes a UI; CSV server exposes files if run). |
| Is it used by anything? | Streamlit is the **primary** interactive surface; CSV server is **optional / manual**. |
| Is it tested? | Streamlit modules have **dedicated tests** (`tests/test_streamlit_*.py`); **4 failures** included Streamlit label assertions on 2026-05-14. |
| Production-ready? | **Streamlit + Docker** documented for internal ops — **not** a hardened public API tier. CSV server is explicitly **local WiFi** use (see script docstring). |
| Necessary for current workflow? | **Streamlit:** valuable but secondary to CLI + SQLite per docs. **REST API:** **not** evidenced as required. |
| Roadmap | **Pause** public API work unless you need external integrations; **keep** Streamlit as ops UI. |

**Supplementary label for CSV server alone:** `PARTIAL_OR_EXPERIMENTAL` (single-purpose, not integrated into RUNBOOK as primary).

---

## 5. Pipeline map (email-pipeline)

**Plain English purpose:** Ingest and retain **OrigenLab’s email archive and Gmail operational mailbox**, derive **business marts and reports**, maintain **lead and marketing contact research**, and enforce **human-reviewed outbound** with **anti-repeat / Sent-folder / suppression** gates — **without** an autonomous send path (`README.md`, `docs/PROJECT_CONTEXT.md`).

Stages below map to your requested numbering. **“Daily-use”** follows `SCRIPT_MAP.md` **OPS_DAILY** lanes where possible.

### Stage 1 — Gmail / archive ingest

| | |
|--|--|
| **Files** | `apps/email-pipeline/scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` (primary Workspace path per `.env.example` comments), `scripts/ingest/04_imap_to_sqlite.py`, `scripts/ingest/02_mbox_to_sqlite.py`, PST path referenced from older phase docs |
| **Input** | Gmail IMAP / mbox / (legacy PST flow) |
| **Output** | Rows in SQLite `emails` (+ related) |
| **DB writes** | **Yes** (ingest) |
| **Cadence** | **Daily-use** for Sent sync on outbound lanes |
| **Tests** | Operator `--help` contract: `apps/email-pipeline/tests/test_operator_entrypoint_contracts.py`; path existence: `tests/test_critical_script_paths.py` |
| **Risks / overlaps** | Titan IMAP vs Gmail Workspace **different `source_file` namespaces** — Streamlit pages may filter Gmail only (called out in `.env.example`) |

### Stage 2 — SQLite canonical storage

| | |
|--|--|
| **Files** | `src/origenlab_email_pipeline/*db*`, `sqlite_migrate`, schema modules, `scripts/tools/apply_sqlite_schema.py` (break-glass) |
| **Output** | SQLite as OLTP |
| **Cadence** | **Core** |
| **Tests** | Many module tests under `tests/` |

### Stage 3 — Mart / build / reporting

| | |
|--|--|
| **Files** | `scripts/mart/build_business_mart.py`, `scripts/commercial/build_commercial_intel_v1.py`, `scripts/reports/*`, `src/origenlab_email_pipeline/business_mart.py`, `commercial_intel_queries.py` |
| **Output** | Derived tables + HTML/JSON reports |
| **DB writes** | **Yes** (rebuild patterns) |
| **Cadence** | **Occasional / maintenance** |
| **Tests** | e.g. `tests/test_business_mart_*.py`, `tests/test_commercial_intel_queries.py` |

### Stage 4 — Lead discovery / import

| | |
|--|--|
| **Files** | `scripts/leads/import_lead_contact_research_csv.py`, `fetch_*.py`, `import_supplier_workbook.py`, `scripts/leads/advanced/import_contact_hunt_to_sqlite.py`, campaign scripts |
| **Output** | `lead_contact_research`, lead_master mutations, files under `reports/out/…` |
| **Cadence** | **Occasional** to **daily** depending on lane |
| **Tests** | Various `tests/test_*lead*` |

### Stage 5 — Matching / scoring

| | |
|--|--|
| **Files** | `scripts/leads/match_leads_to_mart.py`, `scripts/leads/leads_score.py`, `scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py`, root wrappers `scripts/match_lead_accounts_to_existing_orgs.py` |
| **Cadence** | **Occasional / maintenance** |
| **Overlaps** | **Duplicate entrypoints** by design: root shims delegate to `leads/advanced/` (`test_operator_entrypoint_contracts.py` documents this) |

### Stage 6 — Outbound safety memory / do-not-repeat

| | |
|--|--|
| **Files** | `scripts/qa/export_do_not_repeat_master.py`, `scripts/qa/export_outreach_contacted_all.py`, `scripts/qa/export_all_known_marketing_contacts.py`, `scripts/qa/refresh_outbound_safety_memory.py`, modules `core.outbound.do_not_repeat_master`, gate / preflight in `candidate_export_gate.py`, `outbound_sent_preflight.py` |
| **Output** | CSV/JSON under `reports/out/active/current/` and `active/` roots |
| **DB reads** | **Yes**; exports are read-heavy |
| **Cadence** | **Daily-use** for refresh + DNR |
| **Tests** | Multiple outbound / gate tests |

### Stage 7 — Candidate export

| | |
|--|--|
| **Files** | `scripts/leads/export_next_marketing_recipients.py`, `scripts/leads/process_broad_marketing_contacts.py`, `scripts/leads/export_lead_contact_research_queue.py`, `scripts/qa/export_gate_audit_csv.py` |
| **Output** | `send_ready*.csv`, audit CSVs |
| **Cadence** | **Daily-use** |

### Stage 8 — Draft / batch generation

| | |
|--|--|
| **Files** | Tatiana scripts under `scripts/tatiana/`, `scripts/leads/build_manual_html_outreach_batch.py`, `scripts/leads/build_archive_send_batch.py` |
| **Output** | Draft packages / HTML batches |
| **Cadence** | **Lab / campaign-specific** vs **archive lane** |
| **Boundary** | `docs/TATIANA_LAB_BOUNDARY.md` — Tatiana not interchangeable with daily lanes |

### Stage 9 — Manual send / Gmail sender

| | |
|--|--|
| **Files** | Human send (default); `scripts/qa/send_inline_html_email_via_gmail_api.py` (**break-glass**, can send) |
| **Cadence** | **Rare / intentional** for API send |

### Stage 10 — Post-send ingest and refresh

| | |
|--|--|
| **Files** | `scripts/leads/mark_sent_batch_contacted.py`, `scripts/leads/backfill_contacted_from_gmail_sent.py`, `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py`, `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` (break-glass) |
| **Cadence** | **Daily-use** mark + Sent ingest |

### Stage 11 — Streamlit / operator UI

| | |
|--|--|
| **Files** | `apps/business_mart_app.py`, `src/origenlab_email_pipeline/streamlit_*.py` |
| **DB** | SQLite |
| **Cadence** | **Daily / weekly** operator preference |
| **Tests** | Many `tests/test_streamlit_*.py` (**failures observed** — see §2) |

### Stage 12 — Research automation / deep research

| | |
|--|--|
| **Files** | `scripts/research/run_deep_research_prospecting.py`, evidence QA scripts under `scripts/qa/audit_research_candidate_evidence.py`, `verify_research_candidate_evidence.py` |
| **Output** | Timestamped dirs under `reports/out/active/current/research_automation/` (examples present in repo tree) |
| **Cadence** | **Daily / heavy** modes per `SCRIPT_MAP.md` — **stops before send** |

### Stage 13 — Migration / Postgres future work

| | |
|--|--|
| **Files** | `alembic/`, `scripts/migrate/*`, `postgres_outbound_audit.py` |
| **Cadence** | **Optional / migration windows** |

---

## 6. Script inventory summary

**Count:** **134** Python files under `apps/email-pipeline/scripts/` (`find … -name '*.py'` sorted).

### 6.1 Buckets (aligned to your taxonomy)

| Bucket | Count guidance | Notes |
|--------|----------------|-------|
| **KEEP_DAILY** | ~12–15 entrypoints | Listed in `SCRIPT_MAP.md` “Daily lanes” + `tests/test_operator_entrypoint_contracts.py` `_HELP_ENTRYPOINTS` |
| **KEEP_CORE** | Leads import/export, workspace prep, campaign orchestrator | `prepare_outbound_campaign_workspace.py`, `run_current_campaign_pipeline.py`, etc. |
| **KEEP_AUDIT** | `scripts/qa/audit_*`, `export_*audit*`, `check_*` | Many read-only or stdout-only |
| **KEEP_MAINTENANCE** | Mart/commercial rebuilds, dedupe maintenance | Includes `scripts/maintenance/dedupe_canonical_gmail_messages.py` (also in `test_critical_script_paths.py`) |
| **KEEP_MIGRATION** | `scripts/migrate/*`, `validate_sqlite_archive_for_postgres.py` | Break-glass Postgres |
| **KEEP_EXPERIMENTAL** | `scripts/ml/*`, much `tatiana/`, `dataset/`, exploratory `leads/advanced/*`, `campaigns/*` | Per `TATIANA_LAB_BOUNDARY.md` / `SCRIPT_MAP.md` LAB |
| **ARCHIVE_CANDIDATE** | Duplicative **documented** shims | Root `scripts/build_lead_account_rollup.py` etc. are **explicit compatibility wrappers** — **do not archive** until operators migrate (forbidden by current contract tests) |
| **DELETE_CANDIDATE_ONLY_IF_CONFIRMED** | **None recommended** from this audit | Insufficient evidence any script is dead; repo has explicit anti-deletion guidance in `SCRIPT_INVENTORY.md` |

### 6.2 Per-script deep table

A **full 134-row** matrix (each script × doc refs × test grep × overlap) belongs in a **generated** artifact (e.g. output of `scripts/qa/plan_script_consolidation.py`). This audit defers to:

- `apps/email-pipeline/docs/SCRIPT_MAP.md` (canonical)
- `apps/email-pipeline/docs/SCRIPT_INVENTORY.md` (grouped)
- `apps/email-pipeline/scripts/qa/plan_script_consolidation.py` (read-only planner)

**Notable overlap (documented):** two workspace prep stories — `scripts/qa/prepare_outbound_campaign_workspace.py` vs `scripts/leads/advanced/prepare_active_workspace.py` (`SCRIPT_MAP.md` §“Two workspace prep stories”).

---

## 7. Feature necessity matrix

| Feature | Business problem | Needed now? | If removed/paused | MVP/core? |
|---------|------------------|-------------|---------------------|-----------|
| **SQLite + Gmail ingest** | Sent-folder truth, archive signal | **Yes** | Breaks anti-repeat / gates | **Yes** |
| **Shared export gate + DNR** | Prevent accidental repeat outreach | **Yes** | **Critical safety regression** | **Yes** |
| **Two outbound lanes** (volume + precision) | Operational marketing + curated leads | **Yes** | Loses structured cadence | **Yes** |
| **Streamlit business mart** | Operator review without SQL | **High value** | More CLI friction | **Useful** (not strictly required for batch-only shops) |
| **Postgres + Alembic** | Long-term archive / multi-consumer | **No** for daily ops | None if unused | **Advanced/future** |
| **Optional Postgres audit** | Central audit of batches | **No** unless compliance wants it | None if flag off | **Advanced** |
| **REST API** | Integrations | **Not implemented** | N/A | **No** |
| **Deep research automation** | Scale prospect research pre-human review | **Useful** | Manual research only | **Useful** — keep behind guards |
| **Lead scoring scripts** | Prioritization | **Varies** | Weaker ordering | **Useful** |
| **Tatiana drafting** | Faster human drafts | **Lab / pilot** per boundary doc | No effect on gates | **Not MVP** for outbound safety |
| **Gmail API sender script** | Programmatic send | **Rare** | Manual send still works | **Keep but break-glass only** |
| **Reports / client packs** | Client-facing narratives | **Useful** | Less reporting | **Useful** |
| **Commercial intel v1** | Supplier/commercial overlays | **Useful** | Narrower intel | **Useful** |
| **contact_master / archive lane** | Warm revival from archive | **Supported** lane | Shrinks TAM of revive | **Useful** not always daily |
| **CSV web server** | Client WiFi sharing | **Niche** | Use file share instead | **Low** |
| **ML exploration** | Clustering / embeddings experiments | **Research** | None on ops | **Lab** |

---

## 8. Core architecture recommendation

**Principle:** The repo already points at the right shape: **`src/origenlab_email_pipeline` = core library**, **`scripts/` = thin CLIs**, **`docs/SCRIPT_MAP.md` = operator index** (`docs/README.md`, `QUALITY_AND_REFACTOR_STRATEGY.md`).

### 8.1 Target mental model (adapted to repo reality)

| Target | Should hold |
|--------|-------------|
| **core/db** | SQLite access, migrations, RO helpers (`core.sqlite_migrate`, settings) |
| **core/outbound** | Gate, DNR, preflight, contacted state, CSV contracts (already partially mirrored under `core/outbound`) |
| **core/leads** | `leads_schema`, `lead_contact_research`, rollups |
| **core/mart** / **core/reporting** | Mart builders + report generators (incremental move only) |
| **core/safety** | Redaction, safety helpers (`core/safety.py` per `SCRIPT_MAP.md`) |
| **cli/daily** | `SCRIPT_MAP.md` OPS_DAILY rows only |
| **cli/audit** | `scripts/qa/audit_*`, `export_*audit*` |
| **cli/migration** | `scripts/migrate/*` + archive validators |
| **cli/experimental** | `tatiana/`, `ml/`, niche `campaigns/` |

**Do not force** a big-bang folder move until Phase 5; docs already warn against mass import rewrites.

### 8.2 What should stay CLI-only

Anything requiring **operator intent**, **secrets**, or **high blast radius**: ingest, purge, Postgres migrate, send, `--apply` imports.

### 8.3 What should move toward “archive/lab”

- **Tatiana + ML + dataset** paths (already labeled LAB)
- **One-off campaign reconcilers** under `scripts/leads/campaigns/` once campaigns end (process move, not delete)

### 8.4 Test first (before refactors)

1. Fix **4 failing tests** (restore CI green) — `tests/test_outreach_ingest_sync.py`, `tests/test_streamlit_prioridad_copy.py`, `tests/test_streamlit_prioridad_handoffs.py`.
2. **Operator contracts** — `tests/test_operator_entrypoint_contracts.py`, `tests/test_critical_script_paths.py`.
3. **Gate / outbound** — any tests referencing `candidate_export_gate`, `outbound_sent_preflight`, `outreach_contact_state`.

---

## 9. Risks

| Risk | Rank | Evidence / notes |
|------|------|-------------------|
| **Accidental duplicate outreach** (gate bypass) | **Critical** | Central business risk described in `OUTBOUND_SOURCE_OF_TRUTH.md` / `PROJECT_CONTEXT.md` |
| **Sent history not ingested** | **Critical** | `SCRIPT_MAP.md`: Gmail Sent into `emails` **required** for safety |
| **Wrong recipient / contact memory** | **High** | Multiple CSV stages + DB sidecars; operator errors possible |
| **SQLite / Postgres divergence** | **Medium** | Optional Postgres not primary OLTP |
| **Scripts writing unexpectedly** | **Medium** | Mitigated by `--apply`, break-glass headers (`test_operator_entrypoint_contracts.py`); still human-dependent |
| **Test drift** (green ≠ truth) | **Medium** | **4 pytest failures** on 2026-05-14 |
| **API/security exposure** | **Low today** | No public REST; CSV server + Streamlit are **internal** — still guard ports/creds |
| **Sprawl / cognitive load** | **High** | 134+ scripts; two workspace prep stories |
| **Ownership of `reports/out`** | **Medium** | Documented policies in `reports/out/README.md` + planner scripts |

---

## 10. Next action plan (phased)

### Phase 1 — Stabilize and understand SQLite + email pipeline

| | |
|--|--|
| **Inspect** | `apps/email-pipeline/docs/RUNBOOK.md`, `docs/SCRIPT_MAP.md`, `docs/OUTBOUND_SOURCE_OF_TRUTH.md` |
| **Tests** | `uv run pytest -q` — **goal: 0 failures** |
| **Success** | Operators can follow **one** daily lane doc without cross-reading five extras |
| **Do not touch yet** | Postgres migrate scripts production targets |

### Phase 2 — Reduce script/file mess (organization only)

| | |
|--|--|
| **Inspect** | Output of `uv run python scripts/qa/plan_script_consolidation.py` (read-only) |
| **Tests** | Re-run `test_operator_entrypoint_contracts.py` after any path moves |
| **Success** | Fewer “where do I run this?” questions; **no behavior change** |
| **Do not touch** | Gate logic semantics |

### Phase 3 — Decide Postgres continuation

| | |
|--|--|
| **Inspect** | `docs/pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md`, `scripts/migrate/sqlite_archive_to_postgres.py` |
| **Tests** | `uv run pytest -q tests/test_sqlite_archive_to_postgres_migrate.py` (and siblings) |
| **Success** | Documented **go/no-go**; **`.env.example` + `RUNBOOK.md` § Optional PostgreSQL** document URL vars, resolution order, and scratch-first policy (2026-05-14). |
| **Do not touch** | SQLite as source of truth until an explicit cutover decision |

### Phase 4 — Decide API need

| | |
|--|--|
| **Inspect** | Consumer demand (external systems); today **no REST** |
| **Success** | Written ADR: “no API until X” |
| **Do not build** | speculative FastAPI layer |

### Phase 5 — Refactor into cleaner core

| | |
|--|--|
| **Inspect** | `docs/QUALITY_AND_REFACTOR_STRATEGY.md`, `src/origenlab_email_pipeline/core/` |
| **Tests** | Vertical-by-vertical; `tests/test_core_import_surface.py` |
| **Success** | New modules prefer `core.*`; scripts shrink |
| **Avoid** | mass moves without test updates |

---

## 11. Appendix — files and commands inspected

### 11.1 Key files read (partial contents)

- `/home/rafael/dev/freelance/origenlab/README.md`
- `/home/rafael/dev/freelance/origenlab/docs/PROJECT_CONTEXT.md`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/pyproject.toml`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/.env.example`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/alembic/env.py`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/alembic/versions/*.py` (glob listing)
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/docker-compose.yml`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/apps/business_mart_app.py` (header imports)
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/docs/README.md`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/docs/SCRIPT_MAP.md` (first ~150 lines)
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/docs/SCRIPT_INVENTORY.md`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/tests/test_operator_entrypoint_contracts.py`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/tests/test_critical_script_paths.py`
- `/home/rafael/dev/freelance/origenlab/apps/email-pipeline/scripts/leads/advanced/run_contact_hunt_web_server.py` (header + imports)

### 11.2 Commands run

```bash
find /home/rafael/dev/freelance/origenlab/apps/email-pipeline/scripts -name '*.py' -type f | sort
```

```bash
cd /home/rafael/dev/freelance/origenlab/apps/email-pipeline && uv run pytest -q
```

Result (tail): **4 failed, 1024 passed, 7 skipped** (2026-05-14).

### 11.3 Searches

- Workspace ripgrep: `postgres|postgresql|psycopg|alembic|SQLAlchemy` (many hits; authoritative subset cited in §3)
- Workspace ripgrep: `FastAPI|flask|APIRouter|uvicorn|starlette` → **no Python matches**
- Grep `postgres_outbound_audit` / `write-postgres-audit` paths
- Glob `**/alembic/**/*.py`, `apps/web` top-level docs (high-level)

---

## Chat summary (short)

| Question | Answer |
|----------|--------|
| **Postgres real/partial/used?** | **Partial:** real Alembic + migrate loaders + optional audit; **not** the primary app database. |
| **API exists?** | **No** product REST API; Streamlit + optional tiny CSV HTTP server only. |
| **Real core?** | **SQLite + Gmail ingest + outbound gate/safety + two-lane scripts** documented in `SCRIPT_MAP.md`, implemented mainly under `src/origenlab_email_pipeline/`. |
| **Top 5 cleanup actions** | (1) **Fix 4 failing pytest tests** to restore trust (done earlier). (2) **Postgres URL / optional-path docs** — `.env.example` + `RUNBOOK.md` + `SCRIPT_MAP.md` (2026-05-14). (3) **Run `plan_script_consolidation.py`** and reconcile duplicate stories (workspace prep). (4) **Document “no REST API”** in `APP_CONTEXT.md` if stakeholders expect one. (5) **Keep Postgres as optional** until SQLite lanes + tests are pristine. |
