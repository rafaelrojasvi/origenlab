# Reports output (repo-local)

**Git:** Almost everything under `reports/out/` is **ignored** by the root `.gitignore` (only this `README.md` and `.gitkeep` are tracked). That keeps client CSVs, lead hunts, and HTML packs off GitHub by default.

This folder is the **default** destination for generated reports (HTML + JSON).

**Command reference:** [docs/RUNBOOK.md](../../docs/RUNBOOK.md#m-eprun-path).

<a id="m-repout-operational-trust"></a>
### Operational trust scorecard (`active/`)

[`scripts/qa/audit_operational_trust.py`](../../scripts/qa/audit_operational_trust.py) (y [`publish_gate.py`](../../scripts/qa/publish_gate.py)) escriben **`reports/out/active/operational_trust_scorecard.json`**: resultado JSON de checks (`check_id`, `ok`, `critical`, `message`, `details`). Es un **artefacto generado** en la carpeta operativa `active/` (no es histórico por timestamp); conviene regenerarlo al ejecutar el audit.

El resumen legible en Markdown es **[`docs/generated/operational_trust_scorecard.md`](../../docs/generated/operational_trust_scorecard.md)** (también generado; no editar a mano salvo que el proceso cambie).

**Contraste:** Carpetas `full_*` u otros informes bajo `reports/out/` son **runs** de informe de correo; `client_pack_latest/` es el **último paquete leads** para cliente; `active/` agrega **CSV operativos** + este scorecard JSON como señales de coherencia inmediata. Ver [REPORTING — QA](../../docs/REPORTING.md#m-eprep-leads-qa).

- Generate a new run:

```bash
uv run python scripts/reports/generate_client_report.py
```

- Output structure:
  - Each run writes a timestamped subfolder under `reports/out/`:
    - `index.html`
    - `summary.json`
    - optional artifacts (e.g. `clusters.json`, `business_only_sample.json`) depending on flags.

If you prefer to store reports outside the repo (large datasets), set:

```bash
export ORIGENLAB_REPORTS_DIR=/home/rafael/data/origenlab-email/reports
```

# Reports output — what’s what

## Use this folder for “the” report

**Latest full report (everything in one place):**

- **`full_YYYYMMDD_HHMMSS`** — Created by `uv run python scripts/reports/run_all_reports.py`
- Contains: `index.html`, `summary.json`, `unique_emails.csv`, business filter files, `ALCANCE_INFORME.md` (and `clusters.json` if you used `--embeddings`)

**Which one is current?** The one with the **newest timestamp** (e.g. `full_20260315_212047` = 15 Mar 2026, 21:20:47). Open its `index.html` in a browser.

```bash
# From repo root: open latest report
ORIGENLAB_REPORTS_DIR="$(pwd)/reports/out" uv run python scripts/mart/open_client_report.py --open
```

---

## Other folders (old / test runs)

| Folder | What it is |
|--------|------------|
| **`_archive/`** | Old or test runs moved here so the main list stays clear. Safe to delete or keep for reference. |
| **`full_*`** | Full runs from `run_all_reports.py` — **these are your main reports.** |

---

## Files at this level

- **`unique_emails.csv`** — Standalone export from an older run. Prefer the `unique_emails.csv` inside the latest `full_*` folder (it’s regenerated there by `run_all_reports.py`).
- **`NEXT_STEPS.md`** — Short “what to do after running reports” guide.
- **`README.md`** — This file.

---

## Regenerating “the” report

```bash
cd apps/email-pipeline
uv run python scripts/reports/run_all_reports.py
```

That creates a **new** `full_YYYYMMDD_HHMMSS` folder (or overwrites if you pass `--out reports/out/full_20260315_212047`). To keep old runs, don’t pass `--out` so each run gets its own timestamped folder.
