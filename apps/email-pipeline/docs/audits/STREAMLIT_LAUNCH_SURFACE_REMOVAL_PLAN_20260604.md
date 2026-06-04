# Streamlit launch surface removal plan — 2026-06-04

Status: canonical (read-only inventory + phased parking)  
Parent: [`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md)

**Grep basis (2026-06-04):** `rg -n "streamlit|business_mart_app|8501|--group ui|run_streamlit_lan|STREAMLIT_"` across monorepo tracked paths.

---

## Removed launch surfaces

| Path | Removed in | Notes |
|------|------------|-------|
| **`scripts/tools/run_streamlit_lan.sh`** | **LAN launcher PR (2026-06-04)** | Docs-only references; no CI/tests/Makefile. Local LAN: `streamlit run … --server.address 0.0.0.0 --server.port 8501` |

---

## Launch surface inventory

| Path | References (summary) | Active / legacy | Safe action | PR |
|------|----------------------|-----------------|-------------|-----|
| **Root `README.md`** | Streamlit badge; Quick demo `uv run streamlit` + `:8501` | Was **active-looking** | **Park** — demo → `apps/dashboard` + `apps/api` | **PR 1** ✓ |
| **`apps/email-pipeline/README.md`** | Legacy Streamlit appendix; tree comment | **Legacy** | **Park** — no primary launch path | **PR 1** ✓ |
| **`docs/RUNBOOK.md`** | Legacy Docker section; dashboard stack | Mixed | **Park** — legacy section; active dashboard track | **PR 1** ✓ |
| ~~**`scripts/tools/run_streamlit_lan.sh`**~~ | Was docs-only | **Removed** | **Deleted** | **LAN launcher PR** ✓ |
| **`Dockerfile`** | `README`, `RUNBOOK`, audits. **Not** in CI/workflows | **Legacy** | **Park** — top comment `LEGACY`; no delete yet | PR 4 |
| **`docker-compose.yml`** | Same as Dockerfile; service `business-mart` :8501 | **Legacy** | **Park** — compose header comment; no delete yet | PR 4 |
| **`pyproject.toml` `[dependency-groups] ui`** | CI: `.github/workflows/email-pipeline.yml`, `scripts/check-all.sh`, `CONTRIBUTING.md` | **CI-required** | **Keep** — tests import `streamlit` | — |
| **`apps/business_mart_app.py`** | Tests read source (`test_business_mart_app_ux`, etc.) | **Legacy runtime** | **Keep** — no delete | — |
| **`streamlit_*.py` modules** | `business_mart_app` imports | **Legacy runtime** | **Keep** | — |
| **`tests/test_streamlit_*.py`** | pytest + `--group ui` sync | **CI** | **Keep** | — |

### Grep evidence — `run_streamlit_lan.sh` (pre-removal)

```
apps/email-pipeline/README.md
apps/email-pipeline/docs/audits/*.md (audit cross-refs only)
```

**No** matches in `tests/`, other `scripts/`, `.github/`, `Makefile`, `apps/api`, `apps/dashboard`.

**Conclusion:** Removed 2026-06-04; update docs only — do not restore script without operator request.

### Grep evidence — Docker / compose

```
apps/email-pipeline/README.md, docs/RUNBOOK.md, Dockerfile, docker-compose.yml, audits
```

**No** `.github/workflows` references to `8501`, `business-mart`, or `docker-compose.yml`.

**Conclusion:** Label **legacy**; remove Dockerfile/compose in a later PR when operators confirm no Docker Streamlit deploys.

### Grep evidence — `--group ui`

Required by CI and `tests/test_streamlit_*`. Do **not** remove `ui` group until Streamlit tests retire.

---

## PR history

| PR | Changes |
|----|---------|
| **1** | Park Streamlit in README/RUNBOOK; LEGACY comments on Docker/compose |
| **LAN launcher** | Delete `run_streamlit_lan.sh`; update audit docs + README |
| **4+** | Remove Dockerfile + `docker-compose.yml` |
| **5+** | Drop `--group ui` from CI after Streamlit tests retired |

---

## Non-goals

- No Gmail / Postgres sync / send / mirror / `--apply` behavior changes.
- No deletion of `business_mart_app.py` or `streamlit_*` modules in launcher PR.

---

## Verification

```bash
cd apps/email-pipeline
uv run pytest tests/test_active_stack_docs.py tests/test_module_facade_audit.py tests/test_operator_cli.py -q
uv run origenlab audit-facades -- --fail-on-manual-review
```
