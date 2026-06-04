# Streamlit launch surface removal plan — 2026-06-04

Status: canonical (read-only inventory + phased parking)  
Parent: [`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md)

**Grep basis (2026-06-04):** `rg -n "business_mart_app|streamlit_prioridad_pages|streamlit_prioridad_handoffs|streamlit_page_status|streamlit_draft_helpers"` across `apps/email-pipeline`, `apps/api`, `apps/dashboard`, root docs, `.github`.

---

## Removed launch surfaces

| Path | Removed in | Notes |
|------|------------|-------|
| **`scripts/tools/run_streamlit_lan.sh`** | LAN launcher PR (2026-06-04) | Docs-only; local LAN via `streamlit run … --server.address 0.0.0.0` |
| **`Dockerfile`** | Docker/compose PR (2026-06-04) | Streamlit-only image; not used by CI or active dashboard/API |
| **`docker-compose.yml`** | Docker/compose PR (2026-06-04) | Service `business-mart` on :8501; not CI |
| **`apps/business_mart_app.py`** | Python UI PR (2026-06-04) | Legacy Streamlit entrypoint; not imported by `apps/api` / `apps/dashboard` |
| **`streamlit_prioridad_pages.py`** | Python UI PR (2026-06-04) | Only imported by removed app |
| **`streamlit_prioridad_handoffs.py`** | Python UI PR (2026-06-04) | Session keys live on `read/today_workspace.py` |
| **`streamlit_page_status.py`** | Python UI PR (2026-06-04) | Streamlit-only KPI/status renderer |

**Still active (not Streamlit):** [`docker-compose.dashboard-postgres.yml`](../../docker-compose.dashboard-postgres.yml) — local Postgres for dashboard mirror proof-of-life (:5433).

**Renamed (2026-06-04 naming PR):** `tatiana_copilot/draft_review_helpers.py` (was `streamlit_draft_helpers.py`). **Kept:** `streamlit_*` env-flag helpers in `contact_email_suppression.py` / `lead_contact_research.py`.

---

## Deletion impact table (Python UI — 2026-06-04)

| Target | `apps/api` import? | `apps/dashboard` import? | Test imports | Docs refs | Package runtime imports | Safe delete? |
|--------|-------------------|-------------------------|--------------|-----------|-------------------------|--------------|
| `apps/business_mart_app.py` | No | No | Removed: `test_business_mart_app_ux`, `test_streamlit_api_preview`, `test_contacto_gmail` app loader | README, RUNBOOK, audits (updated) | Imported removed `streamlit_*` UI modules only | **Yes** ✓ |
| `streamlit_prioridad_pages.py` | No | No | Removed: `test_streamlit_prioridad_pages_import`, `test_business_mart_app_ux` | Audits | `business_mart_app` only | **Yes** ✓ |
| `streamlit_prioridad_handoffs.py` | No | No | Removed: handoffs, navigate, page tests; `test_streamlit_today_workspace` → `read/today_workspace` session keys | Audits | `streamlit_prioridad_pages`, `business_mart_app` | **Yes** ✓ |
| `streamlit_page_status.py` | No | No | Removed: `test_streamlit_page_status`, `test_streamlit_api_preview` | Audits | `business_mart_app`, `streamlit_prioridad_pages` | **Yes** ✓ |
| ~~`streamlit_draft_helpers.py`~~ → `draft_review_helpers.py` | No | No | `test_tatiana_draft_review_helpers`, `test_contacto_gmail_source_contract` | Tatiana docs | Library/tests | **Renamed** ✓ |

---

## Launch surface inventory

| Path | References (summary) | Active / legacy | Status |
|------|----------------------|-----------------|--------|
| **Root `README.md`** | Dashboard/API demo | **Active** | Parked Streamlit ✓ |
| **`apps/email-pipeline/README.md`** | Active stack + CLIs | **Active** | Streamlit run block **removed** ✓ |
| **`docs/RUNBOOK.md`** | Dashboard stack | **Active** | Streamlit sections demoted ✓ |
| ~~**`scripts/tools/run_streamlit_lan.sh`**~~ | Was docs-only | **Removed** | Deleted ✓ |
| ~~**`Dockerfile`**~~ | Was docs-only | **Removed** | Deleted ✓ |
| ~~**`docker-compose.yml`**~~ | Was Streamlit :8501 | **Removed** | Deleted ✓ |
| **`docker-compose.dashboard-postgres.yml`** | RUNBOOK dashboard stack | **Active** (mirror dev) | **Keep** |
| **`pyproject.toml` `[dependency-groups] ui`** | CI + remaining Streamlit tests | **CI-required** | **Keep** until draft-helper tests retired |
| ~~**`apps/business_mart_app.py`**~~ | Was legacy local UI | **Removed** | Deleted ✓ |
| ~~**`streamlit_prioridad_*.py`**, **`streamlit_page_status.py`**~~ | Was app imports | **Removed** | Deleted ✓ |
| **`tatiana_copilot/draft_review_helpers.py`** | Tests, borrador export | **Library** | **Keep** (renamed) |
| **`tests/test_today_workspace_read.py`**, **`test_tatiana_draft_review_helpers.py`**, etc. | pytest | **CI** | **Keep** |

---

## PR history

| PR | Changes |
|----|---------|
| **1** | Park Streamlit in README/RUNBOOK |
| **LAN launcher** | Delete `run_streamlit_lan.sh` |
| **Docker/compose** | Delete `Dockerfile`, `docker-compose.yml`; update docs/tests |
| **Python UI** | Delete `business_mart_app.py` + three `streamlit_*` UI modules; drop UI-only tests; guardrails in `test_active_stack_docs.py` |
| **Naming** | `streamlit_draft_helpers` → `draft_review_helpers`; test renames; import guardrails |
| **Next** | Drop `--group ui` from CI when pandas tests no longer need the group |

---

## Non-goals

- No Gmail / Postgres sync / send / mirror / `--apply` behavior changes.
- No changes to `apps/api` or `apps/dashboard` runtime code.
- Do not remove `docker-compose.dashboard-postgres.yml`.
- Do not remove `pyproject.toml` `ui` group in the Python UI PR (draft-helper tests still need `streamlit`).

---

## Verification

```bash
cd apps/email-pipeline
uv run pytest \
  tests/test_active_stack_docs.py \
  tests/test_module_facade_audit.py \
  tests/test_operator_cli.py \
  tests/test_package_import_boundaries.py \
  -q
uv run origenlab audit-facades -- --fail-on-manual-review
```
