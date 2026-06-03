# Pipeline outputs — what exists and where

One place to see **what was run**, **what each file contains**, and **what’s visuals vs numbers**.

---

## Quick map: script → outputs

| What | Script | Output(s) | Visuals | Numbers |
|------|--------|-----------|---------|--------|
| **Main client report** | `generate_client_report.py` | `client_report/index.html`, `summary.json`, (optional) `clusters.json` | Charts (year, classification, equipment), tables (domains, senders, cotiz×year, cotiz∧equipo) | Totals, %, top-N lists |
| **Embedding clusters in report** | same, when `--embeddings-sample > 0` | Table in HTML + `clusters.json` | Cluster table (id, size, sample subjects) | n_sample, n_clusters |
| **Stratified clusters (no_bounce)** | `explore_email_clusters.py --sample-mode no_bounce` | `clusters_no_bounce.json` | — | Keyword hit rates, cluster sizes, sample subjects |
| **Stratified clusters (cotiz)** | `explore_email_clusters.py --sample-mode cotiz` | `clusters_cotiz.json` | — | Same |
| **KMeans + Agglomerative + HDBSCAN + equipment regex** | `email_ml_explore.py` | `ml_explore.json` | — | kmeans_k, kmeans_clusters, agglomerative_k, hdbscan (clusters + noise_points), equipment_model_mentions |
| **ML report (visuals)** | `build_ml_report.py` | `ml_report.html` | Bar chart (equipment mentions), KMeans cluster cards with subject lists, summary (HDBSCAN, k) | Same as ml_explore.json, in HTML |

When you run **`run_all.sh`**, it produces one batch folder with: the client report (HTML + JSON + optional clusters), the two stratified cluster JSONs, and `ml_explore.json`. So “everything” for a run is under that batch folder.

---

## What the main report includes (index.html + summary.json)

The script orchestrates output; **SQL metric helpers** live in `origenlab_email_pipeline.client_report_metrics`, and **shared attachment business-doc / delivery-noise SQL** in `origenlab_email_pipeline.attachment_report_sql` (same fragments as `scripts/validation/validate_attachments.py`).

- **Totals:** total messages, with_date, with_body, bounce_like (heuristic).
- **By year:** volume per year (chart + table).
- **By year × cotización:** messages with “cotiz…” per year (chart + table).
- **Classifications:** cotización, proveedor, factura/invoice, pedido/OC, universidad, rebote/NDR (chart + table, %).
- **Equipment:** microscopio, centrífuga, balanza, HPLC, etc. (chart + table, %).
- **Cotización ∧ equipo:** cross counts (e.g. cotiz ∧ balanza).
- **Dominios:** who sends most (all + operational without NDR), Para/Cc (all + external without labdelivery), remitentes exactos.
- **Embeddings sample (if run):** note + **cluster table** (cluster id, size, sample subjects) and link to `clusters.json`.

So: **visuals** = charts and tables in the HTML; **numbers** = same in `summary.json`.

---

## What “done” vs “not run” means

| Item | Done when | Not run / skipped |
|------|-----------|-------------------|
| **SQL + dominios** | You ran `generate_client_report.py` (with or without `--fast`) | `--fast` = dominios skipped; no report = nothing. |
| **Embeddings + cluster table in report** | `--embeddings-sample > 0` (e.g. 3500) | `--embeddings-sample 0` or default in run_all without `WITH_EMBEDDINGS=1` |
| **clusters.json** | Same as above | Same |
| **clusters_no_bounce.json** | `run_all.sh` step 2/4 ran and wrote explore_clusters.json | You ran only generate_client_report, or step failed |
| **clusters_cotiz.json** | `run_all.sh` step 3/4 ran and wrote explore_clusters.json | Same |
| **ml_explore.json** | `run_all.sh` step 4/4 or you ran `email_ml_explore.py` | You didn’t run the script |
| **KMeans** | Always in `email_ml_explore.py` output | — |
| **HDBSCAN** | In `ml_explore.json` if `hdbscan` is installed (`uv sync --group ml`) | `"skipped": "uv sync --group ml (includes hdbscan)"` in JSON |
| **Equipment model mentions** | Always in `email_ml_explore.py` output | — |

So: **everything** = run `WITH_EMBEDDINGS=1 bash scripts/reports/run_all.sh` after `uv sync --group ml` if you want HDBSCAN numbers too.

---

## One-page overview after a run (batch folder)

After `run_all.sh`, you can open:

- **`client_report/index.html`** — main report (visuals + numbers).
- **`ml_report.html`** — ML visuals: bar chart of equipment mentions, KMeans cluster cards (id, size, sample subjects), HDBSCAN summary. Built from `ml_explore.json` by `build_ml_report.py` (run_all does this automatically).
- **`overview.html`** (if generated) — one page with: what ran, key numbers (totals, KMeans k, HDBSCAN clusters/noise), and links to index.html, ml_report.html, clusters.json, ml_explore.json, etc. See “Batch overview page” below.

---

## Batch overview page

If you run the batch overview script (e.g. from `run_all.sh`), it writes **`overview.html`** in the batch folder. That page:

- Says **what was run** (report, embeddings, no_bounce/cotiz clusters, ML explore).
- Shows **key numbers**: total messages, embedding sample size, KMeans k, HDBSCAN clusters and noise, and link to the full report.
- **Links** to `client_report/index.html`, `client_report/summary.json`, `client_report/clusters.json`, `clusters_no_bounce.json`, `clusters_cotiz.json`, `ml_explore.json` so you have one place to open everything.

Command to build it (usually called by run_all at the end):

```bash
uv run python scripts/mart/build_batch_overview.py --batch /path/to/run_NAME
```

---

## File checklist (per run)

| File | Description |
|------|-------------|
| `client_report/index.html` | Main report (charts, tables, cluster table if embeddings ran). |
| `client_report/summary.json` | All report numbers (totals, by_year, classifications, equipment, domains, embeddings_note, cluster_summary if any). |
| `client_report/clusters.json` | Embedding clusters (sample subjects per cluster); only if embeddings ran. |
| `client_report/clusters_no_bounce.json` | Stratified clusters (no_bounce sample); only if run_all step 2 ran. |
| `client_report/clusters_cotiz.json` | Stratified clusters (cotiz sample); only if run_all step 3 ran. |
| `ml_explore.json` | KMeans + Agglomerative + HDBSCAN (if installed) + equipment regex; only if run_all step 4 or email_ml_explore ran. |
| `ml_report.html` | HTML with bar chart (equipment mentions) and KMeans cluster cards; only if build_ml_report.py was run (run_all does it). |
| `overview.html` | One-page summary + links; only if build_batch_overview.py was run. |

This way you can tell at a glance what was done and where to look for visuals and numbers.

---

## Future derived insights (backlog)

Ideas for **additional** report slices using the same columns (subject, body, sender, recipients, date). Not implemented as first-class outputs until prioritized. **Full narrative (archived):** `ARCHIVE/research/DERIVED_INSIGHTS_OPTIONS.md`.

### Already in current reports

Volume/time, classifications, sender domains, keyword aggregates, cotización ∧ equipment crosses, unique emails — see tables above.

### Backlog ideas (high level)

| Idea | Use |
|------|-----|
| Equipment × university / institution | Which equipment themes appear with uni traffic |
| Equipment × sender domain | Per-domain equipment mix |
| University relations rollup | Domains + volume + top equipment |
| Domain → sector mapping | Volume and equipment by segment |
| Top recipient domains | Who we send to (parse To/Cc) |
| Equipment by year | Trends per `eq_*` flag |
| Supplier domain ↔ equipment | Explicit supplier×equipment table |
| Equipment co-occurrence | Pairs of `eq_*` in same message |
| Model regex by domain/sector | Extend `email_ml_explore` patterns |

**Suggested build order:** equipment×domain and equipment×university first; then university rollup; then recipient domains; then sector mapping; then time trends; then supplier/co-occurrence/model-by-domain.

For implementation detail per idea, see `ARCHIVE/research/DERIVED_INSIGHTS_OPTIONS.md` or extend `generate_client_report.py` / streaming passes as needed.
