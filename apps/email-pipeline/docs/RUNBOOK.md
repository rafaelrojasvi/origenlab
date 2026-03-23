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

<a id="m-eprun-legacy"></a>
## Legacy filenames

Old run aliases were removed during the clean-top-level pass; use [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path) as the only run entrypoint.
