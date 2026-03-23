# What to run (in order) — business filter & report

The filter expects table `emails` with at least `id`, `sender`, `recipients`, `subject`, `body`. Point **`ORIGENLAB_SQLITE_PATH`** (or the default under `~/data/origenlab-email/sqlite/emails.sqlite`) at your DB; row counts vary by environment — use `inspect_sqlite.py` to see yours.

---

## 1. Confirm DB and schema (optional)

From repo root:

```bash
cd apps/email-pipeline   # from OrigenLab monorepo root
uv run python scripts/tools/inspect_sqlite.py
```

If the DB path is different on your machine, set it:

```bash
export ORIGENLAB_SQLITE_PATH=/path/to/emails.sqlite
uv run python scripts/tools/inspect_sqlite.py
```

---

## 2. Run filter tests

From repo root:

```bash
uv run pytest tests/test_email_business_filters.py -v
```

Expect 21 passed. Fix any failures before running the filter on the full DB.

---

## 3. Business filter only (artifacts, no HTML report)

**Quick check (e.g. 5k rows):**

```bash
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_sample --limit 5000
```

Output under `reports/out/bf_sample/`: `business_filter_summary.json`, `business_only_sample.json`, `category_counts.csv`, `sender_domain_by_view.csv`.

**Full DB (all rows, no `--limit`):**

```bash
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_full
```

No `--limit` = full table. Output goes to `reports/out/bf_full/` (or set `--out` to e.g. `$HOME/data/origenlab-email/reports/bf_full` if you want it under the same parent as other reports).

---

## 4. Client report with business filter section

This runs the normal client report (SQL aggregates, domains, etc.) and **also** runs the business filter and adds the filter section to the HTML.

**Faster (filter on a sample of rows):**

```bash
uv run python scripts/reports/generate_client_report.py --with-business-filter --business-filter-sample 30000 --out reports/out/client_bf
```

**Full (filter on all rows — slower):**

```bash
uv run python scripts/reports/generate_client_report.py --with-business-filter --out reports/out/client_bf
```

Report (and filter artifacts) go to the `--out` directory. If you omit `--out`, the report goes to `~/data/origenlab-email/reports/<timestamp>_...` (see config).

---

## 5. Client report without business filter (unchanged behavior)

If you only want the usual report (no filter section, no filter artifacts):

```bash
uv run python scripts/reports/generate_client_report.py --out reports/out/client_only
```

Use `--fast` to skip domain streaming; use `--domain-sample N` to estimate domains on N random rows.

---

## Paths (no extra assumptions)

- **DB**: `ORIGENLAB_SQLITE_PATH` or default `~/data/origenlab-email/sqlite/emails.sqlite`
- **Reports**: `ORIGENLAB_REPORTS_DIR` or default `~/data/origenlab-email/reports`; script `--out` overrides the folder for that run
- **Repo root**: all commands are meant to be run from the project root (where `pyproject.toml` and `scripts/` live)

---

## Suggested order for you

1. **Inspect** (once): `uv run python scripts/tools/inspect_sqlite.py`
2. **Tests**: `uv run pytest tests/test_email_business_filters.py -v`
3. **Filter quick check**: `uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_sample --limit 5000`
4. **Filter full**: `uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf_full`
5. **Client report with filter (sample)**: `uv run python scripts/reports/generate_client_report.py --with-business-filter --business-filter-sample 30000 --out reports/out/client_bf`

Then open `reports/out/client_bf/index.html` (or the path you used for `--out`) to see the “Exact vs Heuristic vs Exploratory” and business filter sections.
