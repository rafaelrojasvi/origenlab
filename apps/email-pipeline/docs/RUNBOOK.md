# Operations Runbook

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-07

Single entrypoint for **how to run** the email pipeline. Deeper design lives in [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow) and domain docs ([`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md), [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md), etc.).

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

For **live** mail for **contacto@origenlab.cl** on **Google Workspace**, the operational ingest path is **[`05_workspace_gmail_imap_to_sqlite.py`](../scripts/ingest/05_workspace_gmail_imap_to_sqlite.py)** with OAuth (see [`docs/ingest/WORKSPACE_GMAIL_IMAP.md`](ingest/WORKSPACE_GMAIL_IMAP.md)). Messages are stored in **`emails`** with **`source_file`** values like **`gmail:contacto@origenlab.cl/...`**.

**Titan (password IMAP)** via **[`04_imap_to_sqlite.py`](../scripts/ingest/04_imap_to_sqlite.py)** ([`docs/ingest/IMAP_CONTACTO.md`](ingest/IMAP_CONTACTO.md)) remains supported for legacy or alternate hosts; those rows use **`imap:...`** prefixes.

In **Streamlit** ([`apps/business_mart_app.py`](../apps/business_mart_app.py)), **Actividad contacto Gmail**, **Casos para revisar**, and **Borrador comercial** when loading from the Gmail inbox filter **`gmail:contacto@origenlab.cl%`**. They do **not** include Titan-ingested rows; use **Salud de datos** (or raw SQL) if you need a mixed view of sources.

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

**Not** the publish-safe QA gate (§4). This is the **technical eligibility** layer for cold-outreach **candidates**: [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py), used by both:

- [`compute_next_marketing_recipients()`](../src/origenlab_email_pipeline/next_marketing_queue.py) — Streamlit **Cola outreach marketing** (`apps/business_mart_app.py`).
- [`export_marketing_from_contact_master.py`](../scripts/leads/export_marketing_from_contact_master.py) — optional export sample from **`contact_master`**.

Shared rules include: valid external email, **not** internal domains, **`contact_email_suppression`**, recipients already seen in **Sent** for the configured Gmail user, **`outreach_contact_state`** in **`contacted`**, **`replied`**, or **`snoozed`**, supplier-domain blocklist, and noise heuristics. Parity between lead and contact paths is intentional—**do not** duplicate policy in the UI.

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

Scripts live under [`scripts/qa/`](../scripts/qa/). Shared checks and helpers: [`operational_trust.py`](../src/origenlab_email_pipeline/operational_trust.py). A **PASS** means every **critical** check in the executed steps succeeded (exit code `0`). A **FAIL** means at least one critical check failed (exit code `1`). Some checks are **non-critical** (they print `FAIL` but do not alone fail the step); the scripts only use **critical** outcomes for exit codes.

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
- **Hunt merged vs current `id_lead` mismatch** — Re-align merged to the current cohort (see [`merge_contact_hunt_enrichment.py`](../scripts/leads/merge_contact_hunt_enrichment.py) docstring and [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa) / [`scripts/README.md`](../scripts/README.md)).
- **Readiness / top20 / cohort** — Re-run [`audit_contact_readiness.py`](../scripts/leads/audit_contact_readiness.py) and related lead scripts so `active/` exports match the hunt.
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
