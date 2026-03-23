# Lead Pipeline (Chile external leads)

The lead pipeline collects and normalizes **external public leads** in Chile (procurement, accredited labs, research centers) into a single SQLite layer. It does **not** modify the email archive or the business mart; it only **reads** `organization_master` to flag which leads are already known.

## What it does

1. **Ingest** — Load raw records from local files (ChileCompra CSV/JSON, INN labs CSV, CORFO centers CSV) into `external_leads_raw`.
2. **Normalize** — Build `lead_master` from raw: org name, contact, domain, region, equipment tags, evidence summary.
3. **Score** — Set `priority_score` (0–10+) and `priority_reason` (explainable).
   - Includes **lab/procurement context** detection even when no explicit equipment tag is found.
4. **Match** — Compare `lead_master` to `organization_master` (domain and name); write `lead_matches_existing_orgs`.
5. **Export** — CSV for weekly review and outreach.
6. **Contact-hunt (v1.2)** — Export a Spanish “hoja de hunting” (`leads_contact_hunt_es.csv`) for manual/semi-asistido contact hunting on the best leads.
7. **Merge + import enrichment (optional)** — After Deep Research (or manual edits), merge into the sheet and load into SQLite so contacts are not “lost” in chat/docs only.
8. **Weekly canonical focus (safe mode)** — Generate one operational CSV + one Spanish summary that classify files by purpose and surface warnings.
9. **Active workspace cleanup** — `prepare_active_workspace.py` archives duplicate English CSVs and regenerable derivatives; optional `--deepsearch` and `--unified`.

See [CHILE_LEAD_SOURCES.md](CHILE_LEAD_SOURCES.md) for source URLs and keyword packs.

## Sources (v1)

| Source | Input | Purpose |
|--------|--------|--------|
| **ChileCompra / Mercado Público** | Local CSV or JSON file | Procurement opportunities; buyer orgs; tender title/URL/dates. |
| **INN accredited labs** | Local CSV file | Accredited laboratories; lab name, area, region, website/contact. |
| **CORFO I+D centers** | Local CSV file | Research/innovation centers; center name, org, region, website, contact. |

v1 uses **file-based ingest only**. No API or crawler.

## Expected input formats

### ChileCompra (CSV or JSON)

- **CSV:** Any columns; commonly used: `id`/`codigo`/`CodigoExterno`, `titulo`/`title`/`nombre`, `comprador`/`buyer`/`organismo`, `url`/`link`, `description`/`descripcion`, `region`, `contacto`/`contacto_email`/`email`, `telefono`.
- **Mercado Público descarga masiva:** files are usually **`;`-separated** with headers such as `NombreOrganismo`, `NombreUnidad`, `Nombre`, `Codigo`, `CodigoExterno`, `Link`, `RegionUnidad`, `ComunaUnidad`. Ingest uses automatic `;` vs `,` detection (`fetch_chilecompra.py`). After fixing ingest, **re-run fetch** for ChileCompra files so `external_leads_raw` stores proper column keys; then `normalize_leads.py`.
- **JSON:** Array of objects, or object with key `data`/`results`/`items`/`licitaciones`/`records`. Each object may have `id`, `codigo`, `titulo`, `comprador`, `url`, etc.

### INN labs (CSV)

Columns (any can be missing): `nombre`, `lab_name`, `organizacion`, `laboratorio`, `area`, `esquema`, `acreditacion`, `region`, `ciudad`, `city`, `sitio`, `website`, `url`, `email`, `contacto_email`, `contacto`, `telefono`, `phone`, `id`, `codigo`.

### CORFO centers (CSV)

Columns (any can be missing): `centro`, `nombre_centro`, `name`, `organizacion`, `org_name`, `institucion`, `region`, `ciudad`, `city`, `sitio`, `website`, `url`, `email`, `contacto_email`, `contacto`, `contact_name`, `director`, `telefono`, `phone`, `fono`, `correo`, `area`, `lineas`, `descripcion`, `id`, `codigo`.

Scripts are resilient to missing optional fields.

## Commands

Run from repo root. DB is the same as the rest of the project (`ORIGENLAB_SQLITE_PATH` or default `~/data/origenlab-email/sqlite/emails.sqlite`).

**Sample files** are in `scripts/leads/samples/` so you can run the pipeline without real data:

- `scripts/leads/samples/chilecompra_sample.csv`
- `scripts/leads/samples/inn_labs_sample.csv`
- `scripts/leads/samples/corfo_centers_sample.csv`

```bash
# Ensure lead tables exist (no ingest)
uv run python scripts/leads/normalize_leads.py --ensure-schema-only

# Ingest from files (use sample files to try the pipeline)
uv run python scripts/leads/fetch_chilecompra.py --file scripts/leads/samples/chilecompra_sample.csv
uv run python scripts/leads/fetch_inn_labs.py --file scripts/leads/samples/inn_labs_sample.csv
uv run python scripts/leads/fetch_corfo_centers.py --file scripts/leads/samples/corfo_centers_sample.csv

# Normalize and score
uv run python scripts/leads/normalize_leads.py
uv run python scripts/leads/leads_score.py

# Match to existing orgs (requires business mart)
uv run python scripts/leads/match_leads_to_mart.py

# Export CSV
uv run python scripts/leads/export_leads_csv.py --out reports/out/leads_export.csv

# Weekly shortlist (high_fit + medium_fit first; excludes low_fit by default)
uv run python scripts/leads/export_leads_shortlist.py --out reports/out/leads_shortlist.csv --limit 200

# QA / inspection
uv run python scripts/leads/inspect_leads_quality.py --top 20

# Client-friendly review CSV (includes archive comparison + existing contacts when available)
uv run python scripts/leads/export_client_review_csv.py --out reports/out/leads_client_review.csv --limit 250

# Contact-hunt sheet (v1.2) for manual/semi-assisted enrichment
uv run python scripts/leads/export_contact_hunt_sheet.py --out reports/out/leads_contact_hunt_es.csv --limit 200

# --- Contact hunt → SQLite (recommended once you have real id_lead + enriched CSV) ---
# 1) Export from YOUR database so id_lead matches lead_master.id (not a sample CSV).
# 2) Merge Deep Research output into that base (same column names as the export).
# 3) Import: stores full row JSON in lead_outreach_enrichment; optional copy of compras → lead_master.
uv run python scripts/leads/merge_contact_hunt_enrichment.py \
  -b reports/out/leads_contact_hunt_es.csv \
  -e path/to/deep_research_enriched.csv \
  -o reports/out/leads_contact_hunt_merged.csv
uv run python scripts/leads/import_contact_hunt_to_sqlite.py \
  --csv reports/out/leads_contact_hunt_merged.csv \
  --promote-procurement

# Re-run normalize after ChileCompra refresh: lead_master.email/phone/contact_name are kept
# when the raw file has no contact fields (your hunt import is preserved).

# Weekly canonical focus package (safe mode, non-destructive)
uv run python scripts/leads/run_weekly_focus.py
# outputs:
# - reports/out/active/leads_weekly_focus.csv
# - reports/out/active/leads_weekly_focus_summary_es.md

# Optional: tidy reports/out/active (archive EN duplicates + *_con_db / *_netnew_*), regenerate deepsearch slice, build unified CSV
uv run python scripts/leads/prepare_active_workspace.py --deepsearch --unified

# Full pipeline (set LEADS_*_FILE to your CSV/JSON paths, or use samples)
export LEADS_CHILECOMPRA_FILE=scripts/leads/samples/chilecompra_sample.csv
export LEADS_INN_FILE=scripts/leads/samples/inn_labs_sample.csv
export LEADS_CORFO_FILE=scripts/leads/samples/corfo_centers_sample.csv
bash scripts/leads/run_leads_pipeline.sh
```

Override DB: `--db /path/to/emails.sqlite` on any script.

## Where outputs go

- **SQLite:** Same DB as email/mart. New tables: `external_leads_raw`, `lead_master`, `lead_matches_existing_orgs`.
- **CSV:** You choose with `export_leads_csv.py --out <path>`. Default in `run_leads_pipeline.sh`: `reports/out/leads_export.csv`.

## Scoring

- **priority_score:** 0–10+ (source strength + procurement intent + research/lab relevance + equipment match + **lab/procurement context** + buyer-kind bonus + contact info).
- **priority_reason:** Short text explaining the score (e.g. `fuente=2.0; licitación=2.0; equipo=0.5; contacto`).

Scoring is deterministic and testable; see `src/origenlab_email_pipeline/leads_score.py`.

### Fit bucket (review classification)

`lead_master.fit_bucket` is a simple review classification:

- **high_fit**: explicit equipment + strong lab/procurement context and/or strong buyer kind (hospital/universidad/agricola)
- **medium_fit**: lab/procurement context without explicit equipment, or equipment without strong context
- **low_fit**: generic procurement rows

## Matching

- **Exact domain:** `lead_master.domain` = `organization_master.domain` → confidence 1.0, `already_in_archive_flag=1`.
- **Normalized name:** Lead org name normalized (lowercase, strip S.A./SpA/Ltda) matched to mart `organization_name_guess` → confidence 0.7.

Matching only **reads** the mart; it does not change `organization_master`.

## What stays manual

- Preparing input files (download ChileCompra data, export INN/CORFO to CSV).
- Reviewing the exported CSV and updating `status` / `review_owner` / `next_action` / `notes` (e.g. via SQL or a future UI).
- Deciding which leads to contact and enrichment.
- For v1.2 contact-hunt: buscar manualmente páginas oficiales de compras/transparencia/laboratorio y rellenar los campos de contacto en `leads_contact_hunt_es.csv` (emails/teléfonos y `evidence_url_*`).

## v1 limitations

- No Streamlit tab; use CSV and SQLite for review.
- No Mercado Público API; file-based ChileCompra only.
- No INN/CORFO crawler; CSV only.
- Duplicate leads (same org from two sources) are not merged; you may see two rows.
- Status/review fields are not updated by the pipeline; manual or future tooling.

## Canonical weekly outputs (safe mode)

**Fuente de verdad:** la base SQLite (`lead_master`, etc.). Los CSV son proyecciones.

### Núcleo operativo en `reports/out/active/`

Mantener solo estos archivos como “activos” de trabajo diario (el script `prepare_active_workspace.py` archiva otros CSV sueltos en `active/`):

- `leads_weekly_focus.csv` — priorización semanal con **`id_lead`**
- `leads_weekly_focus_summary_es.md` — resumen y alertas
- `leads_contact_hunt_current.csv` — hoja de hunting enriquecible
- Opcional: `leads_contact_hunt_for_deepsearch.csv` — input Deep Research / GPT (regenerable)

### Derivados y anexos (no son el núcleo en `active/`)

- Shortlist / client review (EN o ES): regenerar con `export_leads_shortlist.py`, `export_client_review_csv.py`, `export_leads_spanish_csvs.py` — incluyen **`id_lead`** para cruces estables.
- `leads_contact_hunt_current_merged.csv` — salida de `merge_contact_hunt_enrichment.py`. Antes de importar, validar alineación con la base actual:

  ```bash
  uv run python scripts/leads/validate_contact_hunt_alignment.py
  uv run python scripts/leads/import_contact_hunt_to_sqlite.py --csv .../merged.csv \
    --require-aligned-with reports/out/active/leads_contact_hunt_current.csv
  ```

- `leads_active_unified.csv` — opcional (`prepare_active_workspace.py --unified`); se archiva en la siguiente limpieza si queda en `active/`.

### Paquete para cliente (no es operativo interno)

- `reports/out/client_pack_latest/` — generado con `scripts/reports/build_leads_client_pack.py` (`index.html`, `resumen_ejecutivo_es.md`, `anexo_leads.csv`, `summary.json`). Ver **[REPORTING.md](../REPORTING.md#m-eprep-leads)**.

Run `prepare_active_workspace.py` to archive English duplicates (`leads_shortlist.csv` / `leads_client_review.csv`) and other non-core CSVs under `active/`.

Reference-only (do not use as canonical merge base):

- `reports/out/reference/*DEEPRESEARCH*`
- `reports/out/reference/*top_hosp_univ_netnew*`
- `reports/out/archive/leads_export.csv` / `reports/out/archive/leads_export_es.csv` (mass audit dump)

## Lead account rollup (CRM-style accounts)

Roll many `lead_master` rows (tenders) into **accounts** without deleting or rewriting `lead_master` / `external_leads_raw`.

See **[LEAD_ACCOUNT_LAYER.md](LEAD_ACCOUNT_LAYER.md)** for tables, CLI, and sample SQL.

## Publication QA (operational trust)

Before treating the static **client pack** and **`reports/out/active/`** lead exports as ready for external sharing, run the publication gate ([`publish_gate.py`](../../scripts/qa/publish_gate.py)). It checks consistency between SQLite, [`summary.json`](../REPORTING.md#m-eprep-leads), top20/readiness/hunt CSVs, and (unless skipped) evidence URLs. Procedure and failure handling: **[RUNBOOK.md §4](../RUNBOOK.md#m-eprun-publish-qa)**; reporting context: **[REPORTING.md — QA leads](../REPORTING.md#m-eprep-leads-qa)**.

## Planned for v2

- Streamlit “Prospección” / “Leads externos” tab.
- Mercado Público API (ticket-based).
- Optional INN/CORFO HTTP fetch (respectful, compliant).
- Dedupe/merge by org/domain.
- Status updates from UI.
