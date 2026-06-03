# OrigenLab — Email pipeline

Local-first pipeline: **PST → mbox** (`readpst`) → **SQLite** → **JSONL**.  
Code lives in the repo; **put real PSTs and outputs outside the repo** (e.g. `~/data/origenlab-email/` — see [docs/DATA_LOCATIONS.md](docs/DATA_LOCATIONS.md#m-epdata-root)).

- Python **3.12**, managed with **[uv](https://docs.astral.sh/uv/)**
- Optional **ML stack** (PyTorch CUDA, sentence-transformers, FAISS-CPU) for a later embeddings stage — see [ML environment setup](#ml-environment-setup)
- Paths from **environment** (see [`.env.example`](.env.example)); defaults use `$HOME/data/origenlab-email/`

**Agent-first app context:** [docs/APP_CONTEXT.md](docs/APP_CONTEXT.md#m-epapp-start).  
**Operator commands (preferred):** [docs/OPERATOR_COMMAND_SURFACE.md](docs/OPERATOR_COMMAND_SURFACE.md) — unified CLI: `uv run python -m origenlab_email_pipeline.cli --help` (`status`, `daily-health`, `refresh-safety`, `validate-csvs`, `check-readiness`, `post-send-digest`). Raw `scripts/qa/…` paths are advanced fallbacks.  
**Documentation index** (what is canonical vs auto-generated, merges to consider): [docs/README.md](docs/README.md).

**HTTP API:** This package does **not** ship FastAPI. Operator and Postgres mirror HTTP live in [`apps/api`](../api/README.md) on port **8001** (`GET /mirror/*` for mirror reporting). The React dashboard [`apps/dashboard`](../dashboard/README.md) uses operator routes only.

## GitHub & what not to commit

This monorepo is meant to hold **code and docs** only; **operational data stays outside git** by default.

| Committed | Not committed (see root + app `.gitignore`) |
|-----------|-----------------------------------|
| `pyproject.toml`, `uv.lock`, `src/`, `scripts/`, `tests/`, `docs/`, `apps/` | `.env` (use [`.env.example`](.env.example) as template) |
| `LICENSE`, `README.md`, [docs/SECURITY.md](docs/SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md) | `*.sqlite`, `*.pst`, `*.mbox`, `*.jsonl` |
| `reports/out/README.md` + `reports/out/.gitkeep` | Everything else under `reports/out/` (reports, `active/` CSVs, client pack — often sensitive) |

**After cloning:** `uv sync` → `cp .env.example .env` → create `~/data/origenlab-email/...` and set paths.

**Never paste** API keys, OAuth tokens, mailbox passwords, full paths to customer archives, or excerpts from real reports into issues or PRs.

**Monorepo (repo root):** coordinated disclosure → [`SECURITY.md`](../../SECURITY.md); general contribution flow → [`CONTRIBUTING.md`](../../CONTRIBUTING.md); license → [`LICENSE`](../../LICENSE). Default PR template → [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md).

Pipeline-specific handling notes: [docs/SECURITY.md](docs/SECURITY.md).

## Prerequisites (Ubuntu / WSL)

```bash
sudo apt update
sudo apt install -y pst-utils sqlite3
```

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# then restart shell or: source ~/.bashrc
```

## One-time setup

```bash
cd apps/email-pipeline   # from monorepo root, or use your absolute clone path

uv python install 3.12
uv sync
```

Create data dirs (outside repo):

```bash
mkdir -p ~/data/origenlab-email/{raw_pst,mbox,sqlite,jsonl,logs,tmp}
```

Copy PST files into `~/data/origenlab-email/raw_pst/` (or set `ORIGENLAB_RAW_PST_DIR`).

Optional: copy env template and edit paths:

```bash
cp .env.example .env
# edit .env if not using defaults under ~/data/origenlab-email/
```

## ML environment setup (WSL, project-local venv only)

Use the repo **`.venv`** — do **not** install into system Python. **`pyproject.toml`** pins the ML stack and uses **`tool.uv.sources`** so **torch** resolves from **cu129** (CUDA), not PyPI CPU. **`numpy==2.3.5`** is pinned with ML so a loose upgrade does not break torch (numpy 2.4.x + this torch build caused import errors in practice).

### Recommended: one command

```bash
cd apps/email-pipeline
export UV_HTTP_TIMEOUT=300
export UV_HTTP_RETRIES=5

uv python install 3.12
uv sync --group ml --group dev   # installs default deps + pinned ML (CUDA torch) + pytest
```

Lockfile **`uv.lock`** is the canonical reproducible snapshot. To save a flat list (e.g. for diffing):

```bash
uv pip freeze > requirements-lock.txt
```

### Real embedding smoke test (GPU)

Downloads **all-MiniLM-L6-v2** once, encodes sample sentences on **CUDA**:

```bash
source .venv/bin/activate
python scripts/ml/explore_email_clusters.py --help
```

Expect: `device: cuda`, `shape: (3, 384)`, `device: cuda:0`, `OK: embedding smoke test passed`.

### Checks

```bash
python scripts/tools/check_system.py
python scripts/tools/check_torch_cuda.py
python scripts/tools/check_embeddings_stack.py
```

### Manual install (if you avoid `uv sync --group ml`)

Same pins as in **`[dependency-groups] ml`** in `pyproject.toml`. If you run raw **`uv pip install -U sentence-transformers …`** without the cu129 index for torch, PyPI may replace CUDA torch — then restore with:

```bash
uv pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu129 --force-reinstall
uv pip install numpy==2.3.5
```

## Run pipeline (exact commands)

PSTs should live under **`~/data/origenlab-email/raw_pst/`** (or set **`ORIGENLAB_RAW_PST_DIR`**). There is **no SQLite yet** until step 2 finishes.

**1. PST → mbox** (requires `readpst`)

```bash
bash scripts/ingest/01_convert_pst.sh
```

With explicit dirs (overrides env for this run):

```bash
ORIGENLAB_RAW_PST_DIR=/path/to/raw_pst ORIGENLAB_MBOX_DIR=/path/to/mbox bash scripts/ingest/01_convert_pst.sh
```

**2. mbox → SQLite**

```bash
uv run python scripts/ingest/02_mbox_to_sqlite.py
```

Each run **clears the `emails` table** then re-imports from mbox (full refresh). **Original PST/mbox is never touched.**

**Optional: live mailbox (IMAP)** — `contacto@origenlab.cl` is on **Titan** (`imap.titan.email`), not Gmail API. Set `ORIGENLAB_IMAP_*` in `.env` and append into SQLite (does not clear the whole DB unless you pass `--replace-source` for that IMAP source only):

```bash
uv run python scripts/ingest/04_imap_to_sqlite.py --folder INBOX --since-days 90 --skip-duplicate-message-id
```

Details: [docs/ingest/IMAP_CONTACTO.md](docs/ingest/IMAP_CONTACTO.md).

**Google Workspace (Gmail) for contacto@** — use OAuth + Gmail IMAP (not Titan):

```bash
# Add `workspace` alongside other groups you already use, e.g.:
uv sync --group ml --group workspace --group dev
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder INBOX --since-days 30 --skip-duplicate-message-id
```

Setup: [docs/ingest/WORKSPACE_GMAIL_IMAP.md](docs/ingest/WORKSPACE_GMAIL_IMAP.md). Overview: [docs/ingest/GMAIL_API.md](docs/ingest/GMAIL_API.md).

## Business mart (client-facing searchable layer)

Build a curated, searchable business layer on top of the raw archive (does **not** modify `emails/attachments/attachment_extracts`).

1) Build / rebuild mart tables:

```bash
cd apps/email-pipeline
uv run python scripts/mart/build_business_mart.py --rebuild
```

Optional: override internal domains:

```bash
uv run python scripts/mart/build_business_mart.py --rebuild --internal-domain labdelivery.cl
```

2) Run Streamlit MVP UI (Streamlit and pandas live in dependency group **`ui`** — not installed by default `uv sync`):

```bash
uv sync --group ui   # once per machine / after clone
uv run --group ui streamlit run apps/business_mart_app.py
```

**Share on Wi‑Fi (same LAN):** Streamlit must listen on all interfaces, and if you use **WSL2** Windows must forward the chosen port to WSL (same idea as other local dev ports).

```bash
# From repo root — binds 0.0.0.0:8501 (override with STREAMLIT_PORT=8502)
bash scripts/tools/run_streamlit_lan.sh
```

On **Windows (PowerShell as Admin)**, replace `172.17.x.x` with your current WSL IP (`hostname -I` in WSL) and `8501` if you changed the port:

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8501 connectaddress=172.17.34.203 connectport=8501
New-NetFirewallRule -DisplayName "WSL Streamlit 8501" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
```

Then the client opens **`http://<your-PC-WiFi-IPv4>:8501/`** (e.g. `http://192.168.4.182:8501/`).  
**Note:** Streamlit has no built-in Basic Auth like the CSV helper; treat this as trusted-LAN only or put a reverse proxy in front.

### Docker (Streamlit only)

The [`Dockerfile`](Dockerfile) runs **only** the business mart Streamlit app. It does **not** containerize ingest, reports, or the website. Build **from `apps/email-pipeline/`** (required context for `COPY pyproject.toml` / `COPY apps/...`):

```bash
cd apps/email-pipeline
docker build -t origenlab-business-mart .
docker run --rm -p 8501:8501 \
  -e ORIGENLAB_DATA_ROOT=/data/origenlab-email \
  -v "$HOME/data/origenlab-email:/data/origenlab-email:ro" \
  origenlab-business-mart
```

Or: `docker compose up --build` using [`docker-compose.yml`](docker-compose.yml) (set `ORIGENLAB_HOST_DATA_ROOT` if your data is not under `$HOME/data/origenlab-email`). See [`docs/RUNBOOK.md`](docs/RUNBOOK.md#m-eprun-docker-streamlit) for env vars, compose notes, and Windows paths.

Docs: `docs/pipeline/BUSINESS_MART.md`

**3. SQLite → JSONL**

```bash
uv run python scripts/ingest/03_sqlite_to_jsonl.py
# Include Phase 2 clean body fields (writes emails_phase2.jsonl by default):
uv run python scripts/ingest/03_sqlite_to_jsonl.py --phase2
```

**LabDelivery / drafting-style cohort** — historical outbound from **@labdelivery.cl** is where Tatiana Vivanco’s writing usually lives in this archive. Scripts default to that domain via [`config/voice_sender_domains.txt`](config/voice_sender_domains.txt) (no env needed). Optional: narrow to specific addresses with `config/tatiana_senders.local.txt` or `ORIGENLAB_TATIANA_SENDERS`. Run with cwd **`apps/email-pipeline`**.

Dataset and ML scripts print **progress bars on stderr** and a **`[compute]`** block: PyTorch/CUDA availability, GPU name when present, and whether **this step** uses the GPU (SQLite scans are CPU-only; **sentence-transformers** can use CUDA when installed).

```bash
# Discover where “Tatiana” / “Vivanco” appear (subjects, bodies, From lines):
uv run python scripts/dataset/audit_tatiana_identity_signals.py

uv run python scripts/dataset/report_tatiana_cohort_metrics.py
# Widen cohort with signature/display-name hits on company domains:
uv run python scripts/dataset/report_tatiana_cohort_metrics.py --include-tatiana-text-signals

uv run python scripts/dataset/export_tatiana_review_sample.py -o reports/out/tatiana_review_sample.csv

# Full candidate cohort CSV + JSON summary (ranked scores, not stratified sampling):
# See docs/dataset/TATIANA_REVIEW_COHORT.md
uv run python scripts/dataset/export_tatiana_candidate_cohort.py --exclude-noise --include-tatiana-text-signals
```

**Inspect DB** (schema, counts, 3 sample rows; body truncated):

```bash
uv run python scripts/tools/inspect_sqlite.py
# or: uv run python scripts/tools/inspect_sqlite.py /path/to/other.sqlite
```

**Explore embeddings + clusters** (ML group; needs `emails.sqlite`):

```bash
uv sync --group ml
# Default sample excludes common NDR/bounces (clearer clusters than raw random).
uv run python scripts/ml/explore_email_clusters.py --limit 600 --n-clusters 12
# Unfiltered random slice of the archive:
uv run python scripts/ml/explore_email_clusters.py --limit 600 --sample-mode random --n-clusters 12
# Senders in config/voice_sender_domains*.txt (e.g. labdelivery.cl); drops ***SPAM*** / [SPAM] subjects by default:
uv run python scripts/ml/explore_email_clusters.py --limit 400 --sample-mode voice --n-clusters 8
# Include tagged-spam subjects (many are phishing that spoof @labdelivery.cl):
uv run python scripts/ml/explore_email_clusters.py --limit 400 --sample-mode voice --voice-include-tagged-spam --n-clusters 8
# Include rows that match body phishing heuristics (default voice mode drops them):
uv run python scripts/ml/explore_email_clusters.py --limit 400 --sample-mode voice --voice-include-likely-phishing --n-clusters 8
# Sparse voice cohort (default min rows is 3 for voice; use --min-rows 2 only if you accept tiny samples):
uv run python scripts/ml/explore_email_clusters.py --limit 400 --sample-mode voice --min-rows 2 --n-clusters 4
# Only rows that look like business signal (cotización, proveedor, factura, …):
uv run python scripts/ml/explore_email_clusters.py --limit 400 --filter-any --n-clusters 8
```

Prints keyword hit rates on the sample and per-cluster subject lines + a body snippet so you can see how well cotizaciones/proveedores separate from noise.

### Client report (HTML + JSON, saved per run)

**Why you don’t see it in the repo tree:** reports default to **`~/data/origenlab-email/reports/`** (same place as SQLite), not inside `origenlab-email-pipeline/`. Open that folder in the editor, or run `uv run python scripts/mart/open_client_report.py --open`. To generate **inside** the repo: `--out reports/out/mi_run` (see [reports/README.md](reports/README.md)).

Full dashboard: by year, cotización / proveedor / universidad / equipment mentions, top sender & recipient domains, optional embedding sample.

```bash
# Fast pass (big DB): aggregates only — seconds
uv run python scripts/reports/generate_client_report.py --fast --name cliente_2025

# With domain tables from random sample (tune N to taste)
uv run python scripts/reports/generate_client_report.py --domain-sample 500000 --name cliente_2025_full

# Optional clusters (ML): adds clusters.json
uv run python scripts/reports/generate_client_report.py --domain-sample 300000 --embeddings-sample 1500 --embeddings-clusters 12
```

Output folder: **`ORIGENLAB_REPORTS_DIR`** (default `~/data/origenlab-email/reports/<timestamp>_<name>/`) with `index.html` (open in browser), `summary.json`. See [docs/REPORTING.md](docs/REPORTING.md#m-eprep-mail).

**Todo en una pasada** (informe + clusters estratificados + ML explore):  
`bash scripts/reports/run_all.sh` — ver [docs/RUNBOOK.md](docs/RUNBOOK.md#m-eprun-batch) (sección batch). Al terminar, en la carpeta del run se genera **`overview.html`**: una sola página con qué se ejecutó, números principales y enlaces a todos los resultados. Mapa completo de salidas: [docs/reporting/OUTPUTS_OVERVIEW.md](docs/reporting/OUTPUTS_OVERVIEW.md).

**Full run (all rows, all CPUs for dominios, ETA en consola):**

```bash
uv sync --group ml   # optional: embeddings en --full
uv run python scripts/reports/generate_client_report.py --full --name cliente_full
# Dominios: un proceso por núcleo (spawn). SQL: 1 pasada fusionada + 1 para año×cotiz.
# Sin embeddings:   --full --embeddings-sample 0
```

More ML + **estratificación** (`--sample-mode cotiz|no_bounce|universidad`): [docs/ml/AI_ML_IMPLEMENTED_SUMMARY.md](docs/ml/AI_ML_IMPLEMENTED_SUMMARY.md)

```bash
uv run python scripts/ml/explore_email_clusters.py --limit 2000 --sample-mode no_bounce --n-clusters 12
uv run python scripts/ml/email_ml_explore.py --limit 5000 --out reports/out/ml.json
```

Append embedding exploration into the same folder:

```bash
uv run python scripts/ml/explore_email_clusters.py --limit 1500 --report-dir ~/data/origenlab-email/reports/<that_folder>
```

## Rebuild after fixing body extraction (HTML fallback)

**Do not delete** your PST or mbox tree — that is the source of truth.

1. Optional: move aside old derived files (or delete them):

   ```bash
   mkdir -p ~/data/origenlab-email/backup_pre_html
   mv ~/data/origenlab-email/sqlite/emails.sqlite ~/data/origenlab-email/backup_pre_html/ 2>/dev/null || true
   mv ~/data/origenlab-email/jsonl/emails.jsonl ~/data/origenlab-email/backup_pre_html/ 2>/dev/null || true
   ```

2. Re-import from mbox (slow; same as first time):

   ```bash
   uv run python scripts/ingest/02_mbox_to_sqlite.py
   uv run python scripts/ingest/03_sqlite_to_jsonl.py
   ```

3. Check non-empty bodies:

   ```bash
   sqlite3 ~/data/origenlab-email/sqlite/emails.sqlite \
     "SELECT COUNT(*) FROM emails WHERE length(trim(coalesce(body,'')))>0;"
   ```

`body` now includes **plain text** and, when there is no plain part, **text stripped from HTML**. `body_html` holds raw HTML when present.

## Inspect SQLite

Default DB: `~/data/origenlab-email/sqlite/emails.sqlite` (or `ORIGENLAB_SQLITE_PATH`).

```bash
sqlite3 ~/data/origenlab-email/sqlite/emails.sqlite "SELECT COUNT(*) FROM emails;"
sqlite3 ~/data/origenlab-email/sqlite/emails.sqlite \
  "SELECT subject, sender, date_iso FROM emails ORDER BY id DESC LIMIT 10;"
```

## Environment variables

| Variable | Default |
|----------|---------|
| `ORIGENLAB_DATA_ROOT` | `$HOME/data/origenlab-email` |
| `ORIGENLAB_RAW_PST_DIR` | `$DATA_ROOT/raw_pst` |
| `ORIGENLAB_MBOX_DIR` | `$DATA_ROOT/mbox` |
| `ORIGENLAB_SQLITE_PATH` | `$DATA_ROOT/sqlite/emails.sqlite` |
| `ORIGENLAB_JSONL_PATH` | `$DATA_ROOT/jsonl/emails.jsonl` |

## SQLite schema (`emails`)

| Column | Description |
|--------|-------------|
| `id` | Autoincrement |
| `source_file` | Mbox file path |
| `folder` | Parent directory |
| `message_id` | Message-ID header |
| `subject` | Subject |
| `sender` | From |
| `recipients` | To + Cc + Bcc (concatenated) |
| `date_raw` | Raw Date header |
| `date_iso` | Parsed ISO datetime when possible |
| `body` | Best plain text: `text/plain` parts, else HTML → text |
| `body_html` | Raw `text/html` parts concatenated (may be empty) |

## Layout

```
origenlab-email-pipeline/
├── .env.example
├── pyproject.toml
├── README.md
├── apps/
│   └── business_mart_app.py      # Streamlit UI (mart + equipment explorer)
├── docs/                         # Detailed docs (BUSINESS_MART, REPORTING, RUNBOOK, ML, etc.)
├── reports/
│   └── out/                      # Generated outputs; contents gitignored except README + .gitkeep
├── scripts/                      # CLI entrypoints (see scripts/README.md)
│   ├── ingest/                   # PST → mbox → SQLite → JSONL
│   ├── mart/                     # business mart, batch overview, open report
│   ├── reports/                  # client report, run_all, ML report
│   ├── validation/               # phase checks, attachment extraction
│   ├── ml/                       # embeddings, clusters, ML explore
│   ├── tools/                    # inspect DB, dedupe, export, env checks
│   ├── qa/                       # operational trust / publish gate (see docs/RUNBOOK.md §4)
│   └── README.md
├── src/origenlab_email_pipeline/
│   ├── config.py
│   ├── db.py
│   ├── parse_mbox.py
│   ├── export_jsonl.py
│   ├── business_mart.py
│   ├── business_mart_schema.py
│   ├── attachment_extract.py
│   ├── email_business_filters.py
│   └── ...
└── tests/                        # pytest (test_parse_mbox_body, test_business_mart_app_ux, etc.)
```

All one-off and pipeline commands live in `scripts/`; they are not installed as package entrypoints except the **unified operator CLI** (`python -m origenlab_email_pipeline.cli`). See **[docs/OPERATOR_COMMAND_SURFACE.md](docs/OPERATOR_COMMAND_SURFACE.md)** (preferred entrypoints), **[docs/SCRIPT_MAP.md](docs/SCRIPT_MAP.md)** (daily outbound lanes and break-glass labeling), and **scripts/README.md** for categories. **Lead/client pack publish-safe check:** `uv run python scripts/qa/publish_gate.py` — [docs/RUNBOOK.md](docs/RUNBOOK.md#m-eprun-publish-qa).
