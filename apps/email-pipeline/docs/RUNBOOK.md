# Operations Runbook

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-24

Single entrypoint for **how to run** the email pipeline. Deeper design lives in [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow) and domain docs ([`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md), [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md), etc.).

<a id="m-eprun-path"></a>
## Path and command policy

- Working directory: `apps/email-pipeline/` (from monorepo root: `cd apps/email-pipeline`).
- Prefer environment variables over machine-specific paths (`ORIGENLAB_SQLITE_PATH`, `ORIGENLAB_REPORTS_DIR`, `.env` from [`.env.example`](../.env.example)).
- Sensitive outputs and large artifacts stay **outside** git (default data root `~/data/origenlab-email/` — see [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-root)).

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

<a id="m-eprun-legacy"></a>
## Legacy filenames

Old run aliases were removed during the clean-top-level pass; use [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path) as the only run entrypoint.
