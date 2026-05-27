# Production dashboard smoke checklist (Phase 9E)

Read-only operator checklist after **refresh + deploy**. Does not send email, mutate Gmail, write SQLite/Postgres, or deploy.

## When to run

- After `refresh_render_dashboard_once.sh` (especially with `RUN_CATALOG_MIRROR=1` and `RUN_COMMERCIAL_DEAL_MIRROR=1`)
- After Render deploy of **apps/api** (`:8001`) and **apps/dashboard**
- Before handing the dashboard to operators for the day

## Prerequisites

- Deployed **operator API** base URL (production or staging), e.g. `https://api.origenlab.cl` or local `http://127.0.0.1:8001`
- Deployed **dashboard** URL loads (browser sanity: Today, Negocio, Catálogo open without console errors)
- No secrets in chat logs — smoke output must stay PASS/FAIL + counts only

## Automated smoke (recommended)

From `apps/email-pipeline`:

```bash
uv run python scripts/qa/smoke_dashboard_api_readiness.py \
  --api-base https://YOUR-API-HOST
```

Local API after `uv run` in `apps/api`:

```bash
uv run python scripts/qa/smoke_dashboard_api_readiness.py \
  --api-base http://127.0.0.1:8001
```

Optional machine-readable report (still no secrets):

```bash
uv run python scripts/qa/smoke_dashboard_api_readiness.py \
  --api-base https://YOUR-API-HOST \
  --json-out /tmp/dashboard_smoke_report.json
```

Exit code **0** = PASS, **1** = FAIL.

### What the script checks (GET only)

| Route | Expectation |
|-------|-------------|
| `GET /health` | HTTP 200, `ok: true`, service name present |
| `GET /operator/status` | HTTP 200, `verdict` present, **no** `sqlite_path` in JSON |
| `GET /mirror/commercial/deals` | HTTP 200, `read_only`, `data_source: postgres_mirror`, `total >= 1` |
| `GET /mirror/catalog/products` | HTTP 200, `read_only`, `data_source: postgres_mirror`, `total >= 9` |
| `GET /mirror/catalog/products/serva-blueslick-250ml` | `commercial_history` includes EUR **117.00** and CLP **695000** |
| `GET /mirror/catalog/products/serva-temed-25ml` | `commercial_history` includes EUR **31.00** and CLP **545000** |
| `GET /cases/warm` | HTTP 200 if reachable; `meta.read_only`, known `data_source` |
| `GET /opportunities/equipment` | HTTP 200 if reachable; `meta.read_only`, **empty** `meta.source_path` |

### Safety scan (all JSON bodies)

Must **not** expose populated values for keys such as: `gmail_url`, `source_file`, `source_path`, `body`, `email_body`, `full_text`, `transfer_id`, `operation_id`.

Must **not** contain forbidden substrings (banking, Gmail URLs, RUT markers, etc.) or known prose artifacts (`montoes`, `Monto112`, `decotizar`, `enelectroforesis`, `oportunida de s`, …).

The script does **not** print response bodies, DB paths, Postgres URLs, or credentials.

## Manual UI checklist (5 minutes)

1. **Today** — Operator status card shows a verdict (not blank); warm-case table loads or shows an explicit empty state (not a generic error).
2. **Negocio** — At least one commercial deal row; CEAF×SERVA lines visible on highlight cards when applicable; Spanish status labels (no raw `margin_ok` in UI).
3. **Catálogo** — Product list ≥ 9 rows; open **BlueSlick 250 ml** and **TEMED 25 ml** drawers — commercial history shows CLP/EUR reference amounts (no email bodies, no bank fields).
4. **Equipamiento** — Table or “Fuente de licitaciones no disponible” (distinguish from “zero opportunities”).
5. **Sistema** — Copy mentions canonical Gmail scope vs full archive; no local file paths in the page.

## If smoke fails

| Symptom | Likely fix |
|---------|------------|
| Catalog `total < 9` | Re-run refresh with `RUN_CATALOG_MIRROR=1`; verify Postgres catalog mirror |
| SERVA history amounts missing | Re-run `build_catalog_sqlite.py` + catalog sync; check seed rows |
| Commercial `total < 1` | Re-run with `RUN_COMMERCIAL_DEAL_MIRROR=1` |
| Forbidden key / prose artifact | Fix mirror redaction or catalog builder; do not patch dashboard to hide leaks |
| `sqlite_path` on `/operator/status` | API config leak — fix operator status serializer before go-live |
| Equipment `meta.source_path` set | API must not expose CSV paths to browser |

## Related

- Refresh runbook: [`apps/email-pipeline/docs/REFRESH_RENDER_DASHBOARD_ONCE.md`](../../apps/email-pipeline/docs/REFRESH_RENDER_DASHBOARD_ONCE.md)
- Truth audit: [`DASHBOARD_TRUTH_AUDIT_2026-05-28.md`](./DASHBOARD_TRUTH_AUDIT_2026-05-28.md)
- API mirror smoke (narrower): [`apps/api/scripts/mirror_parity_smoke.py`](../../apps/api/scripts/mirror_parity_smoke.py)

## Tests

```bash
cd apps/email-pipeline
uv run pytest tests/test_smoke_dashboard_api_readiness.py -q
```
