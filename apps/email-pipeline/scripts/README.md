# Scripts

Run from **`apps/email-pipeline/`** with `uv run python scripts/...` or `bash scripts/...`. Not installed as package entrypoints.

## Where to read

| Need | Doc |
|------|-----|
| Commands and workflows | [docs/RUNBOOK.md](../docs/RUNBOOK.md#m-eprun-path) |
| Data flow and layout | [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) |
| Leads / accounts | [docs/leads/LEAD_PIPELINE.md](../docs/leads/LEAD_PIPELINE.md), [docs/leads/LEAD_ACCOUNT_LAYER.md](../docs/leads/LEAD_ACCOUNT_LAYER.md) |

## Folder map

| Directory | Role |
|-----------|------|
| `ingest/` | PST → mbox → SQLite → JSONL |
| `mart/` | Business mart, batch overview, open report |
| `reports/` | Client report, `run_all_reports.py`, `run_all.sh` |
| `validation/` | Phase checks, attachment text extraction |
| `ml/` | Embeddings, clusters, `email_ml_explore` |
| `tools/` | Inspect DB, dedupe, env checks |
| `pipeline/` | Cross-layer runs (e.g. aligned stack) |
| `leads/` | Lead scoring, matching, audits |
