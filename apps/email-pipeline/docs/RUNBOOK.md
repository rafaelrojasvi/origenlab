# Operations Runbook

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-05-14

Single entrypoint for **how to run** the email pipeline. Deeper design lives in [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow) and domain docs ([`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md), [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md), etc.). **Outbound script index + classifications:** [`SCRIPT_MAP.md`](SCRIPT_MAP.md).

<a id="m-eprun-daily-outbound"></a>
## Daily outbound — two lanes

**Where to work:** put **current** campaign inputs and outputs in **`reports/out/active/current/`** only. Other paths under `reports/out/active/` are usually **older batches, overlap exports, or evidence** — treat them as **archive context**, not as the default source for a new DeepSearch round or send list.

**Volume vs lead data:** do **not** import broad **volume marketing** CSV rows into **`lead_contact_research`** unless each row has a real **`lead_id`**. The volume lane uses **`reviewed_marketing_contacts.csv`** and **`send_ready_marketing.csv`** instead.

### A) Volume marketing lane

```bash
cd apps/email-pipeline
uv run python scripts/qa/export_do_not_repeat_master.py
# DeepSearch → reports/out/active/current/reviewed_marketing_contacts.csv
# Deep/Light research automation (review-only; no send):
# - light: non-deep-research model (lower-cost draft discovery)
# - heavy: MUST be true Deep Research model (o4-mini-deep-research or o3-deep-research)
# - web_search + gpt-4o-mini is NOT Deep Research heavy mode
uv run python scripts/qa/validate_campaign_csvs.py \
  --file reports/out/active/current/reviewed_marketing_contacts.csv \
  --kind marketing_contacts --strict
uv run python scripts/leads/process_broad_marketing_contacts.py
# Review send_ready_marketing.csv — send manually or via scripts/qa/send_inline_html_email_via_gmail_api.py
uv run python scripts/leads/mark_sent_batch_contacted.py --batch-file ... --source ... --updated-by ...
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"  # Sent ingest
```

### B) Precision lead lane

```bash
cd apps/email-pipeline
uv run python scripts/leads/run_current_campaign_pipeline.py --stage prepare \
  --campaign-slug YOUR_SLUG --queue-limit 50 --operator you@example.com
# DeepSearch → reports/out/active/current/reviewed_deepsearch.csv (must include lead_id)
uv run python scripts/leads/run_current_campaign_pipeline.py --stage process-reviewed --apply \
  --operator you@example.com
# Review send_ready.csv — send manually or via your usual path
uv run python scripts/leads/run_current_campaign_pipeline.py --stage post-send \
  --source YOUR_SLUG --operator you@example.com
```

### Daily scripts (KEEP_CORE)

Scripts operators touch most often for outbound: **`export_outreach_contacted_all.py`**, **`export_all_known_marketing_contacts.py`**, **`export_do_not_repeat_master.py`**, **`validate_contacted_csv_coverage.py`**, **`validate_campaign_csvs.py`**, **`process_broad_marketing_contacts.py`**, **`run_current_campaign_pipeline.py`**, **`prepare_outbound_campaign_workspace.py`** (when resetting `active/current`), **`export_lead_contact_research_queue.py`**, **`import_lead_contact_research_csv.py`**, **`export_next_marketing_recipients.py`**, **`mark_sent_batch_contacted.py`**, **`05_workspace_gmail_imap_to_sqlite.py`**, optional **`send_inline_html_email_via_gmail_api.py`**. Core library modules: **`candidate_export_gate`**, **`marketing_export_context`**, **`outreach_contact_state`**, **`next_marketing_queue`**, **`csv_contracts`**, **`outbound_core`**, **`outbound_sent_preflight`**.

### Canonical anti-repeat auxiliary refresh sequence

Run this sequence before a new send cycle to keep auxiliary anti-repeat artifacts aligned:

```bash
cd apps/email-pipeline
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"
uv run python scripts/qa/export_outreach_contacted_all.py
uv run python scripts/qa/export_all_known_marketing_contacts.py
uv run python scripts/qa/export_do_not_repeat_master.py
uv run python scripts/qa/validate_contacted_csv_coverage.py --strict
uv run python scripts/qa/check_reports_out_active_hygiene.py
uv run python scripts/qa/check_outbound_readiness.py
```

One-command wrapper (same order, stops on first hard failure):

```bash
cd apps/email-pipeline
uv run python scripts/qa/refresh_outbound_safety_memory.py
# Optional strict mode:
# uv run python scripts/qa/refresh_outbound_safety_memory.py --fail-on-ready-with-warnings
```

Research output modes:

- `--research-output-mode evidence_first`: draft planning only (no model-generated contacts trusted).
- `--research-output-mode direct_csv`: candidate CSV path, still mandatory evidence verification before processing.

### Debug / audit scripts (KEEP_AUDIT, KEEP_DEBUG)

Read-only or hygiene tools: **`export_contacted_lead_overlap_audit.py`**, **`export_gate_audit_csv.py`**, **`export_outreach_volume_rollup.py`**, **`export_supplier_domain_false_positive_audit.py`**, **`check_outbound_readiness.py`**, **`approve_reviewed_deepsearch_rows.py`**, **`backfill_contacted_from_gmail_sent.py`**. Supporting / CI-style: **`print_outbound_run_summary.py`**, **`export_candidate_audit.py`**, **`publish_gate.py`**, etc. Full table: [`SCRIPT_MAP.md`](SCRIPT_MAP.md#debug--audit-scripts-keepaudit--keepdebug).

### One-time maintenance & alternate lanes (CONSOLIDATE, ARCHIVE_CANDIDATE)

Not part of the two daily workflows: archive batch builders (**`build_archive_send_batch.py`**, **`precheck_archive_shortlist_commercial.py`**), **`export_all_known_marketing_contacts.py`** (overlaps do-not-repeat master partially), **`advanced/prepare_active_workspace.py`** (easy to confuse with **`prepare_outbound_campaign_workspace.py`**), and various **`leads/advanced/*.py`** paths. See [`SCRIPT_MAP.md`](SCRIPT_MAP.md#one-time-maintenance--alternate-lanes).

### Do not remove (safety-critical)

**Gate:** `candidate_export_gate` / `GateContext` policy. **Memory:** `outreach_contact_state`. **Truth:** Gmail Sent rows in **`emails`**, suppression tables, **`validate_campaign_csvs` / `csv_contracts`**, **`export_do_not_repeat_master`**, **`import_lead_contact_research_csv`** (precision lane DB apply), **`mark_sent_batch_contacted`** / post-send. Detail: [`SCRIPT_MAP.md`](SCRIPT_MAP.md#do-not-remove-safety-critical).

<a id="m-eprun-path"></a>
## Path and command policy

- Working directory: `apps/email-pipeline/` (from monorepo root: `cd apps/email-pipeline`).
- **Prefer `uv run python scripts/...` (or `uv run bash ...`)** from that directory so the project package and env match CI and [`scripts/README.md`](../scripts/README.md). Paths like `scripts/qa/publish_gate.py` are part of the operational contract; if you relocate scripts, update [`SCHEMA_OWNERSHIP.md`](pipeline/SCHEMA_OWNERSHIP.md) and **`tests/test_critical_script_paths.py`** together.
- **Lead-account tools** — canonical copies live under `scripts/leads/` (`build_lead_account_rollup.py`, `match_lead_accounts_to_existing_orgs.py`, etc.); root-level `scripts/*.py` names are thin wrappers for compatibility ([`scripts/README.md`](../scripts/README.md)).
- Prefer environment variables over machine-specific paths (`ORIGENLAB_SQLITE_PATH`, `ORIGENLAB_REPORTS_DIR`, `.env` from [`.env.example`](../.env.example)).
- Sensitive outputs and large artifacts stay **outside** git (default data root `~/data/origenlab-email/` — see [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-root)).

---

<a id="m-eprun-mailbox-primary"></a>
## Primary mailbox path (Google Workspace Gmail)

For **live** mail for **contacto@origenlab.cl** on **Google Workspace**, the operational ingest path is **[`05_workspace_gmail_imap_to_sqlite.py`](../scripts/ingest/05_workspace_gmail_imap_to_sqlite.py)** with OAuth (see [`docs/ingest/WORKSPACE_GMAIL_IMAP.md`](ingest/WORKSPACE_GMAIL_IMAP.md)). Messages are stored in **`emails`** with **`source_file`** values like **`gmail:contacto@origenlab.cl/...`** (see **Source-of-truth tiers** below).

**Titan (password IMAP)** via **[`04_imap_to_sqlite.py`](../scripts/ingest/04_imap_to_sqlite.py)** ([`docs/ingest/IMAP_CONTACTO.md`](ingest/IMAP_CONTACTO.md)) remains supported for legacy or alternate hosts; those rows use **`imap:...`** prefixes.

In **Streamlit** ([`apps/business_mart_app.py`](../apps/business_mart_app.py)), **Actividad contacto Gmail**, **Casos para revisar**, and **Borrador comercial** when loading from the Gmail inbox filter the same **`gmail:contacto@origenlab.cl/…`** prefix (SQL: `lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'`). They do **not** include Titan-ingested rows; use **Salud de datos** (or raw SQL) if you need a mixed view of sources.

<a id="m-eprun-source-tiers"></a>
### Source-of-truth tiers (Phase 1)

| Tier | `source_file` pattern | Role |
|------|------------------------|------|
| **Canonical operational** | `gmail:contacto@origenlab.cl/%` | Live Google Workspace mailbox — Streamlit operational panels, outbound readiness hints, case queues, conversation export **default**. Refresh with **`05_workspace_gmail_imap_to_sqlite.py`**. |
| **Legacy / reference** | mbox paths containing `contacto@labdelivery` (and other PST/mbox trees) | Historical archive in the same `emails` table — **not** equivalent to the live OrigenLab mailbox for operational metrics. Inspect via **Salud de datos** or pass **`--include-legacy-email-sources`** to `export_email_conversation_intelligence.py`. |
| **Do not** | Full mbox reload via **`02_mbox_to_sqlite.py`** | **Deletes all `emails` rows** before reload — never run against production unless intentional and backed up. |

Read-only segmentation audit: **[`scripts/qa/audit_canonical_contacto_gmail.py`](../scripts/qa/audit_canonical_contacto_gmail.py)**.

---

<a id="m-eprun-post-gmail-ingest"></a>
## Post–Gmail ingest checklist

After **`05_workspace_gmail_imap_to_sqlite.py`** succeeds against the **same** SQLite file your operators use (`ORIGENLAB_SQLITE_PATH` or default under `ORIGENLAB_DATA_ROOT`):

1. **Mount / process** — Confirm Docker or local Streamlit points at that DB path (see [Docker: Streamlit business mart only](#m-eprun-docker-streamlit)).
2. **Safe to inspect immediately (raw `emails`)** — **Actividad contacto Gmail** and **Casos para revisar** read **`emails`** for **`gmail:contacto@...`**. After ingest, reopen or refresh the app so it rereads SQLite; new messages appear without rebuilding marts. If the UI is empty, verify Workspace ingest actually wrote **`gmail:`** rows (not only **`imap:`**).
3. **Rebuild business mart when** — You changed data that feeds organization/contact/document rollups, or Streamlit pages backed by mart tables look wrong. Run **[`build_business_mart.py`](../scripts/mart/build_business_mart.py)** on the host before expecting updated drill-downs (the Docker image does not build the mart).
4. **Rebuild commercial intel when** — You want **Candidatos comerciales**, exports, or signal-driven views to reflect new mail. Run **`build_commercial_intel_v1.py`** (see [Commercial intelligence v1](#m-eprun-commercial-intel-v1); incremental by default, use **`--rebuild`** or **`--reprocess-days`** when you need a broader refresh).
5. **Likely stale until rebuild** — Pages and widgets that join **`emails`** to **mart** or **`commercial_*`** tables may show old rollups or sparse signals until steps 3–4 complete. **Borrador comercial** can use verbatim text from **`emails`** immediately; richer context panels may still lag mart/commercial builds.

---

<a id="m-eprun-docker-streamlit"></a>
## Docker: Streamlit business mart only

Optional container for [`apps/business_mart_app.py`](../apps/business_mart_app.py). **Does not** run ingest, reports, ML, leads QA, or `apps/web`. **SQLite stays on the host** via a bind mount (not baked into the image).

### Build context

Use **`apps/email-pipeline/`** (directory that contains `pyproject.toml`, `Dockerfile`, and `apps/business_mart_app.py`):

```bash
cd apps/email-pipeline
docker build -t origenlab-business-mart .
```

### Run (`docker run`)

Mount the host data tree at **`/data/origenlab-email`** inside the container so it matches **`ORIGENLAB_DATA_ROOT`** (set in the `Dockerfile`):

```bash
docker run --rm -p 8501:8501 \
  -e ORIGENLAB_DATA_ROOT=/data/origenlab-email \
  -v "$HOME/data/origenlab-email:/data/origenlab-email:ro" \
  origenlab-business-mart
```

| Variable | Role |
|----------|------|
| `ORIGENLAB_DATA_ROOT` | Root inside the container; default layout expects `sqlite/emails.sqlite` under it. |
| `ORIGENLAB_SQLITE_PATH` | Optional full path **inside the container** if the DB is not at `$ORIGENLAB_DATA_ROOT/sqlite/emails.sqlite`. |

The image does **not** copy `.env`. Use `-e` / `--env-file` with **container-side** paths (`/data/...`).

Open **http://localhost:8501/**.

### Run (`docker compose`)

[`docker-compose.yml`](../docker-compose.yml) in the same folder:

```bash
cd apps/email-pipeline
# Optional override (default pattern: $HOME/data/origenlab-email)
export ORIGENLAB_HOST_DATA_ROOT="$HOME/data/origenlab-email"
docker compose up --build
```

On **Windows** (Docker Desktop), set `ORIGENLAB_HOST_DATA_ROOT` to the host folder that contains `sqlite/emails.sqlite` (e.g. `C:\Users\you\data\origenlab-email`).

### Limitations

- **UI only** — build the business mart on the host first: [`build_business_mart.py`](../scripts/mart/build_business_mart.py).
- Read-only volume is OK; the app opens SQLite with immutable + query-only mode.
- **Borrador comercial** (Streamlit) is review-only and does not send mail; optional **export** writes under `reports/out/<timestamp>_streamlit_borrador_comercial/`. If the data mount is read-only, use the in-app JSON download instead or mount `ORIGENLAB_REPORTS_DIR` writable.

---

<a id="m-eprun-postgres-optional"></a>
## Optional PostgreSQL (Alembic, archive load, outbound audit)

**PostgreSQL is optional.** Ingest, outbound gates, Streamlit, and day-to-day reporting run against **SQLite** (`ORIGENLAB_SQLITE_PATH` or default under `ORIGENLAB_DATA_ROOT`). Do **not** treat Postgres as required infrastructure unless you have chosen that path explicitly.

**What Postgres is used for in this repo (when enabled):**

1. **Alembic** — DDL/migrations for Postgres schemas (`apps/email-pipeline/alembic/`). Requires `uv sync --group postgres`.
2. **SQLite→Postgres loaders** — `scripts/migrate/*.py` (archive, document master, outbound sidecars). These are **break-glass**: they can **truncate or delete** rows in target Postgres tables; see [`SCRIPT_MAP.md`](SCRIPT_MAP.md#break-glass-scripts).
3. **Optional outbound audit** — some export CLIs accept `--write-postgres-audit` to append audit rows only when requested (CSV/JSON outputs are unchanged if Postgres is absent).

**First-time / safety:** run migrate loaders and destructive replace modes **only on a scratch or non-production Postgres** until you have validated row counts, FK order, and restore procedures. Never point migration scripts at a shared production Postgres instance for the first trial.

**Connection URL — two discovery orders (read carefully):**

| Consumer | Resolution order (first wins) |
|----------|-------------------------------|
| **Alembic** (`alembic/env.py`) | `ALEMBIC_DATABASE_URL`, else `ORIGENLAB_POSTGRES_URL` |
| **Migrate scripts** (`scripts/migrate/sqlite_*_to_postgres.py`) and **optional outbound audit** on export CLIs | CLI `--postgres-url` if passed, else `ORIGENLAB_POSTGRES_URL`, else `ALEMBIC_DATABASE_URL` |

Example URL form: `postgresql+psycopg://user:pass@host:5432/dbname`. Template lines: [`.env.example`](../.env.example) (commented). Deeper design: [`pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md`](pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md), [`pipeline/POSTGRES_SCHEMA_TARGET_V1.md`](pipeline/POSTGRES_SCHEMA_TARGET_V1.md).

<a id="m-eprun-api-slice1"></a>
### Read-only dashboard API (Slice 1 — FastAPI)

**Status:** experimental read-only API over **PostgreSQL mirrors** only. This is **not** a production cutover: SQLite remains authoritative for ingest, gates, and Streamlit.

**Hard limits (v1):**

- FastAPI defaults to **canonical Gmail operational scope** (`mart.*_canonical`). Use `?scope=archive` for full historical mart counts and listings.
- No write endpoints; no email send; no Gmail ingest or mart rebuild over HTTP.
- Does not mutate SQLite (health may **read-only ping** SQLite for dependency checks only).
- Point `ORIGENLAB_POSTGRES_URL` (or `ALEMBIC_DATABASE_URL`) at **scratch/staging Postgres** — never run production migrate loaders against shared prod from this doc.

**Prerequisites:**

```bash
cd apps/email-pipeline
uv sync --group postgres --group api
export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'
uv run alembic -c alembic.ini upgrade head
# Tier A data (scratch only):
uv run python scripts/migrate/sqlite_outbound_sidecars_to_postgres.py --replace --postgres-url "$ORIGENLAB_POSTGRES_URL"
uv run python scripts/migrate/sqlite_mart_core_to_postgres.py --replace --postgres-url "$ORIGENLAB_POSTGRES_URL"
# Loads archive mart (contact_master, …) plus canonical mirrors (*_canonical) from Gmail operativo.
# Canonical-only (fast; does not rescan full archive mart counts):
# uv run python scripts/migrate/sqlite_mart_core_to_postgres.py --replace --tables canonical \
#   --sqlite-db "$ORIGENLAB_SQLITE_PATH" --postgres-url "$ORIGENLAB_POSTGRES_URL"
# Optional: uv run python scripts/migrate/sqlite_document_master_to_postgres.py --replace ...
```

<a id="m-eprun-sync-dashboard-postgres"></a>
#### Refresh Postgres dashboard mirror

After **mart rebuild** (`build_business_mart.py`) or **Gmail refresh** (ingest), SQLite is authoritative but the **FastAPI dashboard reads Postgres mirrors**. Until you sync, the API is **eventually consistent** with Streamlit/SQLite.

FastAPI defaults to **canonical Gmail operational scope**; use `?scope=archive` for full historical mart.

```bash
cd apps/email-pipeline
export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"

uv run alembic -c alembic.ini upgrade head   # once per scratch DB (includes reporting.dashboard_sync_run)

uv run python scripts/sync/sync_dashboard_postgres_mirror.py --dry-run
uv run python scripts/sync/sync_dashboard_postgres_mirror.py
```

Options: `--only outbound`, `--only mart`, `--only canonical`, `--skip-outbound`, `--skip-mart`, `--json-out path`.

Does **not** mutate SQLite, send mail, or run Gmail ingest/mart rebuild.

**Run locally:**

```bash
cd apps/email-pipeline
uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8000 --reload
```

OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

**Example curls:**

```bash
curl -sS http://127.0.0.1:8000/health | jq .
curl -sS 'http://127.0.0.1:8000/dashboard/summary?scope=canonical' | jq .
curl -sS 'http://127.0.0.1:8000/dashboard/summary?scope=archive' | jq .
curl -sS 'http://127.0.0.1:8000/contacts?limit=5&offset=0' | jq .
curl -sS http://127.0.0.1:8000/outbound/readiness | jq .
```

**Endpoints (v1):** `GET /health`, `GET /health/dependencies`, `GET /dashboard/summary`, `GET /contacts`, `GET /organizations`, `GET /outbound/suppressions/emails`, `GET /outbound/contact-state`, `GET /outbound/readiness`.

`/outbound/readiness` reflects **Postgres mirror** tables only and is **eventually consistent** with SQLite/Streamlit until sync is automated.

Design: [`architecture/POSTGRES_API_DASHBOARD_PLAN.md`](architecture/POSTGRES_API_DASHBOARD_PLAN.md).

---

<a id="m-eprun-after-import"></a>
## 1. After import (PST → mbox → SQLite)

After [`02_mbox_to_sqlite.py`](../scripts/ingest/02_mbox_to_sqlite.py) finishes, typical next steps:

### Run report suite in one shot (recommended)

Generates a timestamped folder: unique emails CSV, client HTML + summary, business filter artifacts.

```bash
cd apps/email-pipeline
uv run python scripts/reports/run_all_reports.py
```

Options:

- `--out DIR` — fixed output directory instead of `reports/out/full_YYYYMMDD_HHMMSS`
- `--fast` — skip full domain scan in client report
- `--embeddings` — ML embeddings + clusters (GPU/CUDA + ML deps)
- `--dedupe` — dedupe by Message-ID inside the run

Typical outputs: `unique_emails.csv`, `index.html`, `summary.json`, `ALCANCE_INFORME.md`, `business_filter_summary.json`, `business_only_sample.json`, `category_counts.csv`, `sender_domain_by_view.csv`.

### Deduplicate (recommended first, or use `--dedupe` above)

```bash
cd apps/email-pipeline
uv run python scripts/tools/dedupe_emails_by_message_id.py
```

### Reports à la carte

**Unique emails CSV**

```bash
uv run python scripts/tools/export_unique_emails_csv.py --out reports/out/unique_emails.csv
```

**Business filter report**

```bash
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_full
# sample: --limit 50000
```

**Client report**

```bash
uv run python scripts/reports/generate_client_report.py --fast --out reports/out/client_report
# full domains: omit --fast; optional --embeddings-sample 1500
```

**One-liner (dedupe + unique emails + business filter)**

```bash
cd apps/email-pipeline && \
uv run python scripts/tools/dedupe_emails_by_message_id.py && \
uv run python scripts/tools/export_unique_emails_csv.py --out reports/out/unique_emails.csv && \
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_full
```

---

<a id="m-eprun-batch"></a>
## 2. Full batch run (`run_all.sh`)

Runs client report, stratified clusters, ML explore, and overview. See [`reporting/OUTPUTS_OVERVIEW.md`](reporting/OUTPUTS_OVERVIEW.md) for artifacts.

```bash
cd apps/email-pipeline
uv sync --group ml
chmod +x scripts/reports/run_all.sh
bash scripts/reports/run_all.sh
```

Default batch folder: `~/data/origenlab-email/reports/run_batch_YYYYMMDD_HHMMSS/`

- Open **`overview.html`** first (what ran, links).
- **`client_report/index.html`** — main dashboard.

| Variable | Effect |
|----------|--------|
| `NAME=myclient` | Folder `run_myclient` |
| `WITH_EMBEDDINGS=1` | Embeddings inside step 1 (slower) |
| `ORIGENLAB_REPORTS_DIR` | Where to create `run_*` |
| `ORIGENLAB_SQLITE_PATH` | DB path |

Examples:

```bash
NAME=marzo2025 bash scripts/reports/run_all.sh
WITH_EMBEDDINGS=1 NAME=full_gpu bash scripts/reports/run_all.sh
```

**Not included:** PST → mbox → SQLite (run ingest when raw mail changes). See [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow).

---

<a id="m-eprun-business"></a>
## 3. Business filter + client report (focused flow)

### Inspect DB (optional)

```bash
cd apps/email-pipeline
uv run python scripts/tools/inspect_sqlite.py
# or: export ORIGENLAB_SQLITE_PATH=/path/to/emails.sqlite
```

### Filter tests

```bash
uv run pytest tests/test_email_business_filters.py -v
```

### Business filter only

```bash
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_sample --limit 5000
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_full
```

### Client report with business filter section

```bash
uv run python scripts/reports/generate_client_report.py --with-business-filter --business-filter-sample 30000 --out reports/out/client_bf
uv run python scripts/reports/generate_client_report.py --with-business-filter --out reports/out/client_bf
```

### Client report without filter

```bash
uv run python scripts/reports/generate_client_report.py --out reports/out/client_only
```

**Paths:** DB = `ORIGENLAB_SQLITE_PATH` or default under `~/data/origenlab-email/sqlite/`. Reports = `ORIGENLAB_REPORTS_DIR` or per-run `--out`. See [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-policy).

---

<a id="m-eprun-cold-export-gate"></a>
## Cold outreach export eligibility (shared gate, Phase 1)

**Not** the publish-safe QA gate (§4). This is the **technical eligibility** layer for cold-outreach **candidates**: [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py).

### Canonical operator entrypoints (use these first)

From `apps/email-pipeline/`:

```bash
# Archive lane — full batch (audit, shortlist, precheck, send_ready / review_required)
uv run python scripts/leads/build_archive_send_batch.py --out-dir reports/out/archive/campaigns/archive_send_batch

# Same path, larger shortlist (e.g. 100–200 company-intro rows): tune --shortlist-limit (and --audit-limit if needed).
uv run python scripts/leads/build_archive_send_batch.py --out-dir reports/out/archive/campaigns/archive_send_batch --shortlist-limit 100 --audit-limit 800

# Archive lane — audit CSV + summary only (no shortlist / precheck)
uv run python scripts/leads/build_archive_send_batch.py --audit-only --out-dir reports/out/archive/audits/archive_audit

# Lead lane — next recipients from lead_master (same gate as Streamlit Cola)
uv run python scripts/leads/export_next_marketing_recipients.py -o reports/out/next_marketing.csv

# Optional: write Postgres outbound audit rows (batch + recipients)
uv run python scripts/leads/export_next_marketing_recipients.py \
  -o reports/out/next_marketing.csv \
  --write-postgres-audit \
  --audit-created-by you@example.com

# Optional on archive lane too
uv run python scripts/leads/build_archive_send_batch.py \
  --out-dir reports/out/archive/campaigns/archive_send_batch \
  --write-postgres-audit \
  --audit-created-by you@example.com

# Post-send contacted-state update (SQLite sidecar)
uv run python scripts/leads/mark_sent_batch_contacted.py \
  --batch-file reports/out/active/<batch>/manual_html_outreach_mark_contacted.txt \
  --source manual_html_batch_2026_04_21 \
  --updated-by you@example.com
```

**Shared outbound defaults:** canonical CLIs and preflight resolve the same Gmail user (CLI → `ORIGENLAB_GMAIL_WORKSPACE_USER` → `contacto@origenlab.cl`), the same default Sent folder pair (`[Gmail]/Enviados`, `[Gmail]/Sent Mail`), and the same `GateContext` builders via [`outbound_core.py`](../src/origenlab_email_pipeline/outbound_core.py). Archive builds write an `outbound_run` object (schema v1) into `archive_outreach_build_summary.json` and audit JSON summaries; the lead exporter can write `<stem>_outbound_summary.json` with `--write-outbound-summary` (that file includes **`sent_preflight`**; the lead CLI does **not** write **`sent_preflight`** to disk without **`--write-outbound-summary`**).

**Optional Postgres outbound audit:** `--write-postgres-audit` records one row in `outbound.outbound_batch` plus recipient rows in `outbound.outbound_batch_recipient`. URL resolution is `--postgres-url` → `ORIGENLAB_POSTGRES_URL` → `ALEMBIC_DATABASE_URL` (this matches migrate scripts; **Alembic alone** uses `ALEMBIC_DATABASE_URL` first — see [Optional PostgreSQL](#m-eprun-postgres-optional)). If audit writing is requested and unavailable/failing, the command exits non-zero; CSV/JSON artifacts remain generated and unchanged.

**Sent-history fail-closed preflight (both lanes):** before building a batch, [`outbound_sent_preflight.py`](../src/origenlab_email_pipeline/outbound_sent_preflight.py) checks that SQLite has **matching** Sent rows for that mailbox and folder set and that **`recipients`** parse to at least one address (same predicates as gate Sent blocking). Exports **fail closed** when Sent history is **missing**, **folder-mismatched**, or **unparsable**. **Exit code `3`** means outbound Sent-history preflight failed (stderr lists counts, optional distinct folder sample, and hints). **`--allow-empty-sent-history`** is an explicit, **audited** override on either CLI and should be **rare**. **Discover the exact Gmail Sent label:** `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --list-folders`. **Ingest that folder** (example): `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"`. On success, archive **`archive_outreach_build_summary.json`** includes a top-level **`sent_preflight`** object (`ok`, `override_used`, counts, folders, errors/warnings). Streamlit **Cola outreach marketing** applies the same shared preflight; the **only** override is **`ORIGENLAB_STREAMLIT_ALLOW_EMPTY_SENT_HISTORY=1`** (use only if you accept weaker Sent blocking in the UI). Details: [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md#sent-history-preflight-fail-closed).

**Preflight (read-only):** when ingest or sidecar freshness is uncertain, **run readiness before batch generation**: [`check_outbound_readiness.py`](../scripts/qa/check_outbound_readiness.py) — SQLite presence, core tables, Sent-folder coverage (**same resolution as** `outbound_core`, including **`probe_sent_history`**-style row/recipient counts and a **distinct folder sample** when Sent rows are missing), sidecar row counts, mart freshness, and optional commercial-layer checks (`--strict-commercial-required`). Use `--json-out` for a machine-readable summary; exit code `1` only when the verdict is `not_ready`.

**Operator checklist:** step-by-step canonical lane artifacts, what to review before send, and after-send memory — [`pipeline/OUTBOUND_OPERATOR_CHECKLIST.md`](pipeline/OUTBOUND_OPERATOR_CHECKLIST.md).

**Trust summary printer:** [`print_outbound_run_summary.py`](../scripts/qa/print_outbound_run_summary.py) prints lane, mailbox, sqlite path, Sent folders, counts, and artifact paths from `archive_outreach_build_summary.json` or a lead `*_outbound_summary.json` (`--write-outbound-summary`).

**Gate audit CSV (read-only):** [`export_gate_audit_csv.py`](../scripts/qa/export_gate_audit_csv.py) exports operator-facing eligibility diagnostics with explicit blocker flags (`blocked_by_sent`, `blocked_by_outreach_state`, suppression flags, final eligibility, exclusion reason) without changing gate logic or DB state.

```bash
cd apps/email-pipeline
uv run python scripts/qa/export_gate_audit_csv.py --out /tmp/gate_audit_lead.csv --lane lead --limit 1000
```

**Supplier-domain false-positive audit (read-only):** [`export_supplier_domain_false_positive_audit.py`](../scripts/qa/export_supplier_domain_false_positive_audit.py) lists `supplier_master.domain_norm` rows (the same identities used for outbound `supplier_domain` blocking) and matches them to **upstream-active** `lead_master` domains (`domain_norm` / `domain`). It **does not** change gate logic, `supplier_master`, or SQLite beyond writing the output CSV. Heuristics flag domains that look like government, academic, or institutional buyers when they also have matching high/medium-fit leads—use this to prioritize manual review of supplier exclusions (for example `.gob.cl` agencies that appear as buyers in `lead_master`).

```bash
cd apps/email-pipeline
uv run python scripts/qa/export_supplier_domain_false_positive_audit.py \
  --out reports/out/archive/audits/supplier_domain_false_positive_audit.csv
# Include every supplier domain even when no lead shares that domain (noisy CSV):
uv run python scripts/qa/export_supplier_domain_false_positive_audit.py \
  --out reports/out/archive/audits/supplier_domain_false_positive_audit_all.csv \
  --include-zero-lead-domains
# Optional: --db /path/to/emails.sqlite --limit 5000
```

**How to review the CSV:** sort by `likely_false_positive_reason` (non-empty) and `matching_high_fit_count` / `matching_medium_fit_count`. `recommended_action` is advisory only (`review_supplier_exclusion`, `likely_true_supplier`, `no_matching_leads`, `needs_manual_review`). The script prints a short terminal summary (totals, likely false positives, high/medium impact sum, top 10 domains). **Do not treat output as permission to unblock**—decisions stay in supplier review workflows and data changes outside this export.

**Streamlit** is for **review**, **read/write** on `contact_email_suppression` / `outreach_contact_state`, and **visibility**; it is **not** the final record of what was exported in a given run. **Canonical CLI CSV/JSON** (and optional readiness JSON) are the reproducible record; update **Sent ingest** and **outreach/suppression sidecars** after sends so the next run’s blocker memory stays accurate.

**Recommended post-send sequence:**

1. Send (manual process; this pipeline does not auto-send in canonical export CLIs).
2. Verify send recipient file or manifest.
3. Mark batch contacted in SQLite:

   ```bash
   uv run python scripts/leads/mark_sent_batch_contacted.py \
     --batch-file reports/out/active/<batch>/manual_html_outreach_mark_contacted.txt \
     --source manual_html_batch_2026_04_21 \
     --notes "post-send contact memory update" \
     --updated-by you@example.com
   ```

   Or from a JSON send manifest:

   ```bash
   uv run python scripts/leads/mark_sent_batch_contacted.py \
     --send-manifest /path/to/send_manifest.json \
     --source gmail_api_send_2026_04_21 \
     --updated-by you@example.com
   ```

4. Optionally ingest Sent later as independent evidence (`05_workspace_gmail_imap_to_sqlite.py`).
5. Run `scripts/qa/check_outbound_readiness.py` and/or your gate audit before next export.

**Recommended before importing or sending DeepSearch contacts (read-only checks):**

1. Ingest latest Sent so SQLite reflects what the mailbox actually sent (discover the label first if needed):

   ```bash
   cd apps/email-pipeline
   uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --list-folders
   uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"
   ```

2. Run the **contact overlap audit** (Sent + `outreach_contact_state` + suppressions + `lead_master` / `lead_contact_research`; optional `--input-research-csv` for rows not imported yet):

   ```bash
   uv run python scripts/qa/export_contacted_lead_overlap_audit.py \
     --out reports/out/archive/audits/contacted_lead_overlap.csv
   ```

3. Run the **gate audit** on candidates after overlap review:

   ```bash
   uv run python scripts/qa/export_gate_audit_csv.py \
     --out reports/out/archive/audits/gate_after_overlap.csv --lane lead
   ```

Interpretation: treat **exact email** hits as strong duplicates; **same-domain** and **organization-name** rows are hints only (`confidence` / `recommended_action` in the overlap CSV). This audit does not change SQLite or gate behavior.

### Outbound lanes: volume marketing contacts vs precision `lead_id` research

**Quick commands:** see [Daily outbound — two lanes](#m-eprun-daily-outbound) at the top of this runbook. **Script index:** [`SCRIPT_MAP.md`](SCRIPT_MAP.md).

SQLite remains the **runtime blocker truth** (Gmail Sent + `outreach_contact_state` + suppressions). Gate policy in code is unchanged; these workflows add files and CLIs only.

**Volume lane (expanded):** Use when you want **many net-new institutional emails** without **`lead_id`**. Do **not** import broad rows into `lead_contact_research` unless each row has a real **`lead_id`**. Steps: export **`export_do_not_repeat_master.py`** → attach `do_not_repeat_master.txt` / CSV to DeepSearch → save **`reviewed_marketing_contacts.csv`** → **`validate_campaign_csvs.py --kind marketing_contacts`** → **`process_broad_marketing_contacts.py`** → **`send_ready_marketing.csv`** → send → **`mark_sent_batch_contacted.py`** + Sent ingest. Schema: `institution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal` (`fit_signal` optional). Outputs also include `marketing_safe_to_send.csv`, `marketing_blocked_already_known.csv`, `marketing_needs_manual_review.csv`, `marketing_contacts_summary.json`.

**Precision lane (expanded):** One row per **`lead_id`**. [`export_lead_contact_research_queue.py`](../scripts/leads/export_lead_contact_research_queue.py) produces **`research_queue.csv`**; DeepSearch returns **`reviewed_deepsearch.csv`**; [`run_current_campaign_pipeline.py`](../scripts/leads/run_current_campaign_pipeline.py) runs overlap, import, gate, and **`export_next_marketing_recipients.py`** into **`send_ready.csv`** (see wrapper section below).

**Campaign workspace convention (reduce CSV/report chaos):**

- Active campaign working set should live in **`reports/out/active/current/`** only.
- Prepare/reset this canonical workspace before each campaign:

  ```bash
  cd apps/email-pipeline
  uv run python scripts/qa/prepare_outbound_campaign_workspace.py \
    --campaign-slug q2_hospitals --operator you@example.com
  ```

- If a previous `active/current` run exists, archive it first:

  ```bash
  uv run python scripts/qa/prepare_outbound_campaign_workspace.py \
    --campaign-slug q2_hospitals --operator you@example.com --archive-existing
  ```

- Canonical files created/cleaned in `active/current`:
  `research_queue.csv`, `reviewed_deepsearch.csv`, `overlap_audit.csv`, `gate_audit.csv`, `send_ready.csv`,
  `outbound_summary.json`, `send_manifest.json`, `mark_contacted_result.json`, `campaign_manifest.json`.
- Older campaign artifacts should be kept under `reports/out/archive/...`.
- **Do not use old campaign CSVs as fresh DeepSearch input**; always start from a newly prepared `active/current/research_queue.csv`.

**Recommended wrapper CLI (orchestration, no auto-send):**

- Use [`run_current_campaign_pipeline.py`](../scripts/leads/run_current_campaign_pipeline.py) to orchestrate the existing scripts in the right order over `reports/out/active/current/`.
- DeepSearch stays manual/reviewed (you upload `research_queue.csv` and save reviewed output to `reviewed_deepsearch.csv`).
- Sending stays manual (wrapper does not send email).
- Individual scripts remain available for debugging and advanced control.
- Optional contract checker for campaign CSVs:

  ```bash
  uv run python scripts/qa/validate_campaign_csvs.py --workspace reports/out/active/current --strict
  ```

```bash
cd apps/email-pipeline

# 1) Prepare campaign workspace + export research queue
uv run python scripts/leads/run_current_campaign_pipeline.py \
  --stage prepare \
  --campaign-slug q2_hospitales_labs_02 \
  --operator you@example.com \
  --queue-limit 50 \
  --archive-existing

# 2) After manual DeepSearch review saved to active/current/reviewed_deepsearch.csv
uv run python scripts/leads/run_current_campaign_pipeline.py \
  --stage process-reviewed \
  --operator you@example.com \
  --apply

# 3) After manual send, mark contacted memory (optional Sent ingest)
uv run python scripts/leads/run_current_campaign_pipeline.py \
  --stage post-send \
  --source q2_hospitales_labs_02 \
  --operator you@example.com
```

### Lead contact research queue (DeepSearch / ChatGPT)

Use a deterministic, read-only queue export to target research where high/medium-fit leads still have no trustworthy contact email:

1. **Export research queue**

   ```bash
   cd apps/email-pipeline
   uv run python scripts/leads/export_lead_contact_research_queue.py \
     --out reports/out/active/current/research_queue.csv \
     --limit 1000
   ```

2. **Run DeepSearch/ChatGPT manually** using the suggested `research_query_*` fields in the CSV.
3. **Import reviewed results** into `lead_contact_research` (dry-run first, then apply):

   ```bash
   uv run python scripts/leads/import_lead_contact_research_csv.py \
     --input /path/to/reviewed_contacts.csv
   uv run python scripts/leads/import_lead_contact_research_csv.py \
     --input /path/to/reviewed_contacts.csv \
     --apply \
     --updated-by you@example.com
   ```

4. **Run gate audit** to verify blocker/eligibility impact:

   ```bash
   uv run python scripts/qa/export_gate_audit_csv.py \
     --out /tmp/gate_audit_after_research.csv \
     --lane lead \
     --limit 5000
   ```

5. **Export/send** from canonical lane CLIs (`export_next_marketing_recipients.py` or archive batch path), keeping human review and post-send contacted-state updates.

**Demoted / advanced:**

- [`export_archive_outreach_candidates.py`](../scripts/leads/advanced/export_archive_outreach_candidates.py) — legacy **audit-only** wrapper (prints a note to stderr); prefer `--audit-only` on the builder.
- [`export_marketing_from_contact_master.py`](../scripts/leads/advanced/export_marketing_from_contact_master.py) — **exploratory** `contact_master` export; not the default archive path (see [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md)).

### Manual HTML outreach batch (packaging only)

After you **manually** narrow an archive `review_required` / shortlist CSV, package **one shared HTML body** and a **mark-contacted** file for later `outreach_contact_state` updates. **No send**, **no DB**, **no personalization**.

From `apps/email-pipeline/`:

```bash
uv run python scripts/leads/build_manual_html_outreach_batch.py \
  --input reports/out/active/<your_batch>/archive_manual_send_candidates_v3.csv \
  --html /path/to/origenlab_presentacion_comercial_email_combined.html \
  --subject "OrigenLab · Equipos para laboratorio en Chile" \
  --out-dir reports/out/active/<your_batch>_manual_html_package \
  --batch-name my_run_20260416
```

**Writes (under `--out-dir`):**

| File | Purpose |
|------|---------|
| `manual_html_outreach_recipients.csv` | One row per recipient: `contact_email`, `institution_name`, `domain`, `subject`, `html_source_path`, `batch_name` |
| `manual_html_outreach_send_manifest.json` | Counts, paths, subject, UTC timestamp |
| `manual_html_outreach_mark_contacted.txt` | One email per line (for batch mark after you send) |
| `shared_email.html` | Copy of the shared HTML (omit with `--no-copy-html`) |
| `manual_html_outreach_preview.md` | Short human preview (omit with `--no-preview-md`) |

**After manual send:** ingest Sent if you use that for gate memory, then e.g.:

```bash
uv run python scripts/leads/mark_outreach_state.py \
  --batch-file reports/out/active/<your_batch>_manual_html_package/manual_html_outreach_mark_contacted.txt \
  --state contacted --updated-by <you> --source manual_html_batch
```

Optional: `--limit N` caps recipients after dedupe; duplicate emails (case-insensitive) keep the **first** row’s metadata.

**Archive batch — commercial precheck policy:** default is **advisory** (commercial “drop” → `review_required`). Use `--strict-commercial-drop` to omit those rows from both output CSVs. See `archive_outreach_build_summary.json` keys `commercial_precheck_policy` and `strict_commercial_drop`.

The gate is invoked from:

- [`compute_next_marketing_recipients()`](../src/origenlab_email_pipeline/next_marketing_queue.py) — Streamlit **Cola outreach marketing** (`apps/business_mart_app.py`).
- [`build_archive_send_batch` / archive outreach audit](../src/origenlab_email_pipeline/archive_send_batch_builder.py) — archive lane.
- [`export_marketing_from_contact_master.py`](../scripts/leads/advanced/export_marketing_from_contact_master.py) — optional export sample from **`contact_master`** (advanced).

Shared rules include: valid external email, **not** internal domains, **`contact_email_suppression`**, recipients already seen in **Sent** for the configured Gmail user, **`outreach_contact_state`** in **`contacted`**, **`replied`**, or **`snoozed`**, supplier-domain blocklist, and noise heuristics. The same gate module applies to both paths; **`contact_master`** exports and audit rows for `contact_master` also enable **stricter marketing-noise rules** (e.g. machine-style `reply@…` locals) because the mail graph is noisier than **`lead_master`**. **`export_candidate_audit.py`** evaluates leads and contacts with the matching strictness so CSVs match each export path.

**Operational caution:** Passing the gate means “not auto-rejected by these checks,” not “validated buyer” or “safe for bulk autonomous send.” **`contact_master`** is still a **mail-graph** rollup; many rows remain low-signal for outbound. Prefer **human review** and **small batches**. A fuller **role-state** schema for commercial review remains **deferred**.

### Troubleshooting: few or zero rows from `export_next_marketing_recipients.py`

**Resolve which DB the app uses** (from `apps/email-pipeline/`):

```bash
uv run python -c "from origenlab_email_pipeline.config import load_settings; print(load_settings().resolved_sqlite_path())"
```

**Stage counts on `lead_master`** (upstream-active = not soft-retired for missing raw; predicate matches [`lead_upstream_reconcile.sql_upstream_active`](../src/origenlab_email_pipeline/lead_upstream_reconcile.py)):

```sql
-- Any fit_bucket, must have email
SELECT COUNT(*) FROM lead_master lm
WHERE (COALESCE(NULLIF(TRIM(lm.upstream_sync_state), ''), 'active') != 'retired_no_raw')
  AND NULLIF(TRIM(COALESCE(lm.email_norm, lm.email)), '') IS NOT NULL;

-- Default export also excludes low_fit
SELECT COUNT(*) FROM lead_master lm
WHERE (COALESCE(NULLIF(TRIM(lm.upstream_sync_state), ''), 'active') != 'retired_no_raw')
  AND COALESCE(lm.fit_bucket, 'low_fit') != 'low_fit'
  AND NULLIF(TRIM(COALESCE(lm.email_norm, lm.email)), '') IS NOT NULL;
```

**Manual outreach memory (sidecar, no Sent sync):** to set or reset `outreach_contact_state` explicitly (e.g. after a call), use [`scripts/leads/mark_outreach_state.py`](../scripts/leads/mark_outreach_state.py). `contacted`, `replied`, and `snoozed` **block** cold-export eligibility for that email; `not_contacted` **does not** block and clears first/last timestamps on write.

**Outreach / suppression / Sent footprint:**

```sql
SELECT state, COUNT(*) FROM outreach_contact_state GROUP BY state;
SELECT COUNT(*) FROM contact_email_suppression;
-- Use the same mailbox string as ORIGENLAB_GMAIL_WORKSPACE_USER (default contacto@origenlab.cl):
SELECT folder, COUNT(*) FROM emails
WHERE lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'
GROUP BY folder ORDER BY COUNT(*) DESC;
```

**Gate reasons on a sample:** raise `--lead-limit` and inspect `reject_reasons` in the audit CSV:

```bash
uv run python scripts/qa/export_candidate_audit.py --out /tmp/export_audit.csv --lead-limit 5000 --contact-limit 0
```

### Read-only export audit (CSV)

Samples **lead_master** and **contact_master** rows, runs the **same** gate, and writes one CSV (eligible flag + reject reason). Use for spot checks and regression baselines—not as proof of list quality.

```bash
cd apps/email-pipeline
uv run python scripts/qa/export_candidate_audit.py --out /tmp/export_audit.csv --lead-limit 2000 --contact-limit 2000
```

Optional: `--db /path/to/emails.sqlite`. Interpretation: **eligible** = gate returned no block reason; **reject_reasons** (CSV column) is the first reason code from [`evaluate_export_eligibility()`](../src/origenlab_email_pipeline/candidate_export_gate.py); boolean `*_hit` columns mirror that primary reason. Supplier/noise flags mean the row matched those heuristics—**not** that remaining “eligible” rows are high-intent buyers.

### Regression tests

```bash
cd apps/email-pipeline
uv run pytest tests/test_candidate_export_gate.py -q
uv run pytest tests/test_business_mart_app_ux.py -q
```

---

<a id="m-eprun-publish-qa"></a>
## 4. Publish-safe QA (operational trust gate)

Scripts live under [`scripts/qa/`](../scripts/qa/). Shared checks and helpers: [`operational_trust`](../src/origenlab_email_pipeline/operational_trust/__init__.py) package facade. A **PASS** means every **critical** check in the executed steps succeeded (exit code `0`). A **FAIL** means at least one critical check failed (exit code `1`). Some checks are **non-critical** (they print `FAIL` but do not alone fail the step); the scripts only use **critical** outcomes for exit codes.

**What the gate does *not* do:** It does not prove commercial claims, email deliverability, or that every business fact in a narrative is true. It validates **internal consistency** between the SQLite DB, the latest client pack snapshot, the operational hunt/readiness CSVs, URL shape, and (unless skipped) live HTTP responses for collected links.

### Recommended sequence before sharing lead/client artifacts

1. **Optional — one ordered leads routine** [`scripts/leads/run_leads_operational_stack.sh`](../scripts/leads/run_leads_operational_stack.sh): assigns a UUID `run_id` → optional ingest → ensure schema → normalize → reconcile upstream → score → match → exports → weekly focus → client pack → publish gate → run manifest (e.g. `bash scripts/leads/run_leads_operational_stack.sh --skip-fetch`). Build the business mart first when you need matches (`scripts/pipeline/run_aligned_stack.sh`). **`--skip-gate` completes without publish validation** — treat as **not publish-safe by default** until you run `publish_gate.py`. **`--reconcile-dry-run` only skips reconcile `--apply`**; the rest of the stack still writes DB/files. If publish gate runs and **fails**, the stack still writes `operational_stack_last_run.json` with `publish_gate.passed=false` and exits non-zero.
2. If you did not use the stack: regenerate the client pack when the DB or lead inventory changed: [`build_leads_client_pack.py`](../scripts/reports/build_leads_client_pack.py) → [`reports/out/client_pack_latest/`](../reports/out/README.md).
3. Run the full gate (from `apps/email-pipeline/`) if the stack did not already run it:

   ```bash
   uv run python scripts/qa/publish_gate.py
   ```

4. Treat **external** handoff of the pack + related CSVs as **publish-safe only if the gate PASS** (with evidence HTTP enabled — see below).

**Provenance / run correlation:** `client_pack_latest/summary.json` includes `provenance` with `operational_run_id` when the pack was built inside the stack (same value as `ORIGENLAB_LEADS_OPERATIONAL_RUN_ID`). **`publish_gate_validated_this_artifact` is always false in the pack** — the pack is built before the gate; validation outcome lives in `operational_stack_last_run.json` → `publish_gate` for the same `run_id`. The scorecard JSON `provenance` repeats `operational_run_id` when the gate inherits that env var. A durable copy per run: `reports/out/active/operational_run_manifests/<run_id>.json`. These aid traceability; they **do not** replace `publish_gate` or prove the pack is safe to publish.

### Commands

**Full gate** (runs verify → audit → evidence checks):

```bash
cd apps/email-pipeline
uv run python scripts/qa/publish_gate.py
```

Common options (forwarded / used by substeps):

| Flag | Effect |
|------|--------|
| `--db PATH` | SQLite for comparisons (default: `ORIGENLAB_SQLITE_PATH` / settings) |
| `--max-pack-age-hours N` | Client pack `summary.json` `generated_at_utc` must be ≤ `N` hours old (default `168`; used in audit) |
| `--skip-evidence-http` | **Skips** [`check_evidence_links.py`](../scripts/qa/check_evidence_links.py) entirely (exit `0` for that step). Use for quick internal runs **without** live URL probes. **Do not treat a run with this flag as final publication validation** — external sharing should use a full run **without** `--skip-evidence-http` so evidence URLs are checked. |
| `--evidence-timeout`, `--evidence-max-failures`, `--evidence-max-fail-ratio` | Passed into the evidence step (per-URL timeout, max failing URLs, max failure ratio) |

**Individual scripts** (same working directory):

```bash
uv run python scripts/qa/verify_client_pack_consistency.py
uv run python scripts/qa/audit_operational_trust.py
uv run python scripts/qa/check_evidence_links.py
```

### What each step checks (high level)

| Script | Reads (typical) | Writes | Exit `1` when |
|--------|-----------------|--------|----------------|
| [`verify_client_pack_consistency.py`](../scripts/qa/verify_client_pack_consistency.py) | Pack `summary.json`, SQLite `lead_master`, top20 CSV, hunt + ready/needs CSVs (for **top20** cross-checks only) | stdout only | Any **critical** check fails (pack vs DB totals/fit buckets, top20 vs readiness/hunt/DB — **not** hunt/readiness cohort partition; that runs in audit only) |
| [`audit_operational_trust.py`](../scripts/qa/audit_operational_trust.py) | Same `active/` paths + [`docs/generated/CONTACT_READINESS_AUDIT.md`](generated/CONTACT_READINESS_AUDIT.md) for DB path line | [`reports/out/active/operational_trust_scorecard.json`](../reports/out/README.md), [`docs/generated/operational_trust_scorecard.md`](generated/operational_trust_scorecard.md) | Any **critical** check fails (**cohort partition**, readiness nulls, taxonomy, stale pack, merged vs current hunt IDs, etc.) |
| [`check_evidence_links.py`](../scripts/qa/check_evidence_links.py) | URL columns in top20 + hunt CSVs | stdout only | Invalid `http(s)` URL strings and/or HTTP probe failures beyond [`--max-failures` / `--max-fail-ratio`](../scripts/qa/check_evidence_links.py) |

### When something fails

- **Pack vs DB mismatch** — Regenerate the pack after DB changes: `uv run python scripts/reports/build_leads_client_pack.py`.
- **Stale client pack** — Regenerate the pack or raise `--max-pack-age-hours` only if you intentionally accept an older snapshot.
- **Hunt merged vs current `id_lead` mismatch** — Re-align merged to the current cohort (see [`merge_contact_hunt_enrichment.py`](../scripts/leads/advanced/merge_contact_hunt_enrichment.py) docstring and [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa) / [`scripts/README.md`](../scripts/README.md)).
- **Readiness / top20 / cohort** — Re-run [`audit_contact_readiness.py`](../scripts/leads/advanced/audit_contact_readiness.py) and related lead scripts so `active/` exports match the hunt.
- **Evidence URLs** — Fix or remove bad URLs in the CSVs; adjust thresholds only with care (they are safety limits, not business rules).
- **Provenance / taxonomy warnings** — Some checks are **non-critical**; read the line marked `FAIL` without `[critical]` as advisory.

Further detail: [`REPORTING.md`](REPORTING.md#m-eprep-leads-qa), [`scripts/README.md`](../scripts/README.md).

---

<a id="m-eprun-commercial-intel-v1"></a>
## 5. Commercial intelligence v1

Builds a client-discovery layer on top of the historical archive:

- rebuildable signal facts/rollups
- durable org/contact/opportunity candidates with review statuses
- explainable suppression and rationale fields

```bash
cd apps/email-pipeline
uv run python scripts/commercial/build_commercial_intel_v1.py
```

Useful variants:

```bash
# full recompute of rebuildable signal layer
uv run python scripts/commercial/build_commercial_intel_v1.py --rebuild

# include a recency reprocess window in addition to watermark optimization
uv run python scripts/commercial/build_commercial_intel_v1.py --reprocess-days 30

# reconciliation summary
uv run python scripts/commercial/audit_commercial_intel_v1.py

# export queue slice (CSV/JSON; filters: entity kind, status, candidate_type, min confidence/strength)
uv run python scripts/commercial/export_commercial_candidate_queue.py \
  --out reports/out/commercial_queue.csv --limit 500

# approve / reject / snooze one candidate (writes candidate_manual_override + candidate_review_event)
uv run python scripts/commercial/review_commercial_candidate.py \
  --entity-kind organization --entity-key example.com --action snooze --actor you@example.com
```

Optional UI: the business mart Streamlit app includes **Candidatos comerciales** (read-only by default). Enable writes only with a writable SQLite file and `ORIGENLAB_STREAMLIT_COMMERCIAL_REVIEW_RW=1`.

Contract summary:

- raw archive tables are unchanged
- watermark is performance-only
- correctness uses idempotent rebuild/upsert and reconciliation checks

Design/ownership: [`pipeline/COMMERCIAL_INTEL_V1.md`](pipeline/COMMERCIAL_INTEL_V1.md)

---

<a id="m-eprun-legacy"></a>
## Legacy filenames

Old run aliases were removed during the clean-top-level pass; use [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path) as the only run entrypoint.
