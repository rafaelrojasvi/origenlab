# Email pipeline module facade audit — 2026-06-04

Status: read-only audit (docs/housekeeping only)  
Owner: email-pipeline-maintainers  
Branch context: `docs/email-pipeline-module-facade-audit`

## Summary

This audit reviewed duplicate-looking Python module names under:

- `apps/email-pipeline/src/origenlab_email_pipeline/`
- `apps/email-pipeline/src/origenlab_email_pipeline/core/...`

The main finding is that these are mostly **not** accidental duplicates.

Current pattern:

```text
root module = current implementation
core/... module = stable import facade / re-export
```

| Layer | Role | Typical size |
|-------|------|----------------|
| `origenlab_email_pipeline.<name>.py` | **Canonical implementation** (logic, SQL, rules) | tens–800+ LOC |
| `origenlab_email_pipeline.core.<domain>.<name>` | **Compatibility shim** (`from ..<name> import *` or thin wrapper) | ~8–15 LOC |
| `origenlab_email_pipeline.core.<domain>/` (extracted) | **Some logic moved here** on purpose (mart, broad lane, DNR, reports_out) | varies |

**Import reality (2026-06-04):**

- Production code, scripts, Streamlit, and **`apps/api`** still import **root** paths most often (`config`, `db`, `outbound_core`, `business_mart`, etc.).
- `origenlab_email_pipeline.core.*` is a **documented stable surface** for new code and a few extracted modules; it is **not** a second copy of the whole package.
- Domain subpackages (`commercial/`, `operational_trust/`) follow the same idea: canonical code lives in the subpackage; old root shims were removed in Phase 5I where fan-in was low.

## `core/` subpackages (facade map)

| Subpackage | Facade files (re-export) | Implementation also in `core/` |
|------------|--------------------------|--------------------------------|
| `core/` (top) | `config`, `db`, `sqlite_migrate`, `safety` | `safety`, `reports_out`, `research_automation`, `step_runner` |
| `core/outbound/` | `candidate_export_gate`, `outbound_core`, suppression, CSV contracts, marketing helpers | `broad_marketing_contacts`, `do_not_repeat_master` |
| `core/gmail/` | `gmail_workspace_oauth`, `gmail_send`, `contacto_gmail_source` | — |
| `core/mart/` | `business_mart`, `business_mart_schema` | `build_runner`, `build_business_mart_cli`, builders |
| `core/leads/` | `leads_*`, `lead_*` (many thin shims) | — |
| `core/suppliers/` | `supplier_schema`, `supplier_workbook` | — |

Shim example (`core/config.py`):

```python
from ..config import *  # implementation stays at package root
```

## What is *not* a duplicate

- **`commercial/commercial_intel_*`** — canonical cluster under `commercial/`; root `commercial_intel_*` shims removed after verification.
- **`operational_trust/`** — canonical cluster; root `operational_trust_*.py` shims removed.
- **`core/mart/build_runner.py`** — orchestration extracted from `scripts/mart/build_business_mart.py`; root `business_mart.py` still holds shared helpers used by mart + commercial rules.

## Operator / safety note

This audit **does not** recommend deleting root modules or `core/` shims in a drive-by cleanup. Either side is still imported in the monorepo; removal belongs to a **named migration PR** per domain with tests and doc updates.

See also: [`ROOT_CORE_COMPATIBILITY_AUDIT_20260602.md`](ROOT_CORE_COMPATIBILITY_AUDIT_20260602.md), [`../pipeline/PACKAGE_DOMAINS.md`](../pipeline/PACKAGE_DOMAINS.md), [`../QUALITY_AND_REFACTOR_STRATEGY.md`](../QUALITY_AND_REFACTOR_STRATEGY.md).

## Housekeeping (this PR)

- **`.gitignore`:** ignore `apps/email-pipeline/reports/local/` so ad-hoc operator reports (e.g. daily-health text dumps) are not committed.
- **This file:** short facade audit note for future agents; no runtime or import changes.

## Reusable check

```bash
cd apps/email-pipeline
uv run origenlab audit-facades
uv run origenlab audit-facades -- --json
uv run origenlab audit-facades -- --fail-on-manual-review
```

Read-only: inspects tracked `src/origenlab_email_pipeline/**/*.py` via `git ls-files`; does not import or mutate pipeline data.

## Non-goals

- No file moves, deletions, or refactors.
- No Gmail / Postgres / send / purge / mirror script changes.
- No import path churn in `apps/api` or `apps/dashboard`.
