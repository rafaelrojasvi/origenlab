# Reports (default: outside repo)

HTML/JSON outputs usually go under **`~/data/origenlab-email/reports/`** (see `.env.example` and `ORIGENLAB_REPORTS_DIR`).

**How to generate and what each artifact means:** [docs/RUNBOOK.md](../docs/RUNBOOK.md#m-eprun-path) and [docs/reporting/OUTPUTS_OVERVIEW.md](../docs/reporting/OUTPUTS_OVERVIEW.md). **Pre-share validation (client pack + active CSVs):** [RUNBOOK §4](../docs/RUNBOOK.md#m-eprun-publish-qa).

**Open the latest report from the repo:**

```bash
cd apps/email-pipeline
uv run python scripts/mart/open_client_report.py --open
```

**Repo-local test runs** (gitignored except `reports/out/README.md`):

```bash
mkdir -p reports/out
uv run python scripts/reports/generate_client_report.py --fast --out reports/out/mi_cliente
```
