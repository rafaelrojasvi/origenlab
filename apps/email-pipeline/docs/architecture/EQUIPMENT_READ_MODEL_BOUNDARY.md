# Equipment opportunities — read-model boundary

**Status:** active architecture contract (2026-06)  
**Audience:** API, dashboard, and email-pipeline maintainers  

**Related:**

- [`apps/api/README.md`](../../../api/README.md) — operator API backends and production env
- [`POSTGRES_API_DASHBOARD_PLAN.md`](POSTGRES_API_DASHBOARD_PLAN.md) — broader Postgres + dashboard initiative
- [`apps/api/docs/API_RESPONSE_CONTRACT.md`](../../../api/docs/API_RESPONSE_CONTRACT.md) — response shapes for `GET /opportunities/equipment`

---

## Strategic split

| Layer | Role |
|-------|------|
| **SQLite + local filesystem** | Operational truth: ingest, outbound safety, operator artifacts under `reports/out/active/current` |
| **Postgres (`api.*` views)** | Typed **read model** for API and dashboard in production |
| **CSV queue files** | Export, audit, and operator artifacts — **not** the public HTTP contract |

Production **`GET /opportunities/equipment`** must read **`api.v_equipment_opportunity`** via `ORIGENLAB_API_BACKEND=postgres`. The SQLite/active-current CSV path is **dev/local only**.

---

## Current bridge (acceptable interim)

```
equipment_first_operator_queue_*.csv  (active/current artifact)
        │
        ▼
load_equipment_opportunity_mirror.py
        │
        ▼
commercial.equipment_opportunity_source
commercial.equipment_opportunity
        │
        ▼
api.v_equipment_opportunity   (is_canonical_source = TRUE)
        │
        ▼
apps/api  PostgresEquipmentOpportunityRepository
        │
        ▼
dashboard Today (read-only)
```

CSV remains a valid **input** during the bridge: the mirror loader ingests the canonical queue file into `commercial.*`. The API does **not** open that CSV in production.

---

## Target final state

```
domain pipeline (ingest, enrichment, scoring)
        │
        ▼
typed Postgres read model (commercial.* / api.*)
        │
        ├──► apps/api + dashboard (query views)
        │
        └──► CSV export / audit artifact (generated from read model, not identity source)
```

- **Identity** for an equipment opportunity row: `codigo_licitacion` plus source/detail semantics in Postgres (`extra_json`, ChileCompra fields), **not** the queue CSV filename.
- **`meta.source_path` / `source_path_info`** in API responses: audit/metadata about which mirror artifact row came from — basename-only in JSON; not a stable business key.

---

## Enforcement

| Environment | `ORIGENLAB_API_BACKEND` | Equipment data source |
|-------------|-------------------------|------------------------|
| **Production** (`ORIGENLAB_ENV=production`) | **must be `postgres`** | `api.v_equipment_opportunity` only |
| **Local / CI dev** | `sqlite` (default) or `postgres` | CSV fallback allowed only when backend is `sqlite` |

`apps/api` tests lock this contract:

- Postgres repository SQL references `api.v_equipment_opportunity` and `is_canonical_source = TRUE`.
- Postgres repository does not call `fetch_equipment_opportunities` or read `active_current` CSV.
- `ORIGENLAB_ENV=production` + `ORIGENLAB_API_BACKEND=sqlite` fails at settings validation.
- Route tests prove `api_backend=postgres` serves `meta.data_source=postgres_mirror` without CSV fallback.

---

## Out of scope for this boundary doc

- Removing CSV generation from the email-pipeline (still required for operator audit and mirror ingest).
- Large schema migrations or retiring the bridge loader (follow-up work once read model is sole writer).
