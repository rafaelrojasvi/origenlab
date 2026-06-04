# Streamlit launch surface removal plan — 2026-06-04

Status: canonical (read-only inventory + phased parking)  
Parent: [`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md)

**Grep basis (2026-06-04):** `rg -n "streamlit|business_mart_app|8501|--group ui|run_streamlit_lan|STREAMLIT_"` across monorepo tracked paths.

---

## Removed launch surfaces

| Path | Removed in | Notes |
|------|------------|-------|
| **`scripts/tools/run_streamlit_lan.sh`** | LAN launcher PR (2026-06-04) | Docs-only; local LAN via `streamlit run … --server.address 0.0.0.0` |
| **`Dockerfile`** | Docker/compose PR (2026-06-04) | Streamlit-only image; not used by CI or active dashboard/API |
| **`docker-compose.yml`** | Docker/compose PR (2026-06-04) | Service `business-mart` on :8501; not CI |

**Still active (not Streamlit):** [`docker-compose.dashboard-postgres.yml`](../../docker-compose.dashboard-postgres.yml) — local Postgres for dashboard mirror proof-of-life (:5433).

---

## Launch surface inventory

| Path | References (summary) | Active / legacy | Status |
|------|----------------------|-----------------|--------|
| **Root `README.md`** | Dashboard/API demo | **Active** | Parked Streamlit in PR 1 ✓ |
| **`apps/email-pipeline/README.md`** | Legacy Streamlit appendix | **Legacy** | Local `streamlit run` only ✓ |
| **`docs/RUNBOOK.md`** | Dashboard stack + legacy Streamlit notes | **Mixed** | Docker section → removed notice ✓ |
| ~~**`scripts/tools/run_streamlit_lan.sh`**~~ | Was docs-only | **Removed** | Deleted ✓ |
| ~~**`Dockerfile`**~~ | Was docs-only | **Removed** | Deleted ✓ |
| ~~**`docker-compose.yml`**~~ | Was Streamlit :8501 | **Removed** | Deleted ✓ |
| **`docker-compose.dashboard-postgres.yml`** | RUNBOOK dashboard stack | **Active** (mirror dev) | **Keep** |
| **`pyproject.toml` `[dependency-groups] ui`** | CI + Streamlit tests | **CI-required** | **Keep** |
| **`apps/business_mart_app.py`** | Tests, legacy local UI | **Legacy runtime** | **Keep** |
| **`streamlit_*.py` modules** | App imports | **Legacy runtime** | **Keep** |
| **`tests/test_streamlit_*.py`** | pytest | **CI** | **Keep** |

### Grep evidence — Docker Streamlit (pre-removal, 2026-06-04)

```
.github — no Dockerfile, docker-compose.yml, 8501, business-mart
apps/api, apps/dashboard — no matches
apps/email-pipeline/tests — no matches
```

References were **README**, **RUNBOOK**, **audits**, **`.env.example`** only.

**Conclusion:** Safe to delete `Dockerfile` + `docker-compose.yml`; keep `docker-compose.dashboard-postgres.yml`.

---

## PR history

| PR | Changes |
|----|---------|
| **1** | Park Streamlit in README/RUNBOOK |
| **LAN launcher** | Delete `run_streamlit_lan.sh` |
| **Docker/compose** | Delete `Dockerfile`, `docker-compose.yml`; update docs/tests |
| **Next** | Drop `--group ui` from CI after Streamlit tests retired |

---

## Non-goals

- No Gmail / Postgres sync / send / mirror / `--apply` behavior changes.
- No deletion of `business_mart_app.py` or `streamlit_*` modules.
- Do not remove `docker-compose.dashboard-postgres.yml`.

---

## Verification

```bash
cd apps/email-pipeline
uv run pytest tests/test_active_stack_docs.py tests/test_module_facade_audit.py tests/test_operator_cli.py -q
uv run origenlab audit-facades -- --fail-on-manual-review
```
