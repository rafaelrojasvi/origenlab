# Streamlit launch surface removal plan — 2026-06-04

Status: canonical (read-only inventory + phased parking)  
Parent: [`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md)

**Grep basis (2026-06-04):** `rg -n "streamlit|business_mart_app|8501|--group ui|run_streamlit_lan|STREAMLIT_"` across monorepo tracked paths.

---

## Launch surface inventory

| Path | References (summary) | Active / legacy | Safe action | PR |
|------|----------------------|-----------------|-------------|-----|
| **Root `README.md`** | Streamlit badge; Quick demo `uv run streamlit` + `:8501` | Was **active-looking** | **Park** — demo → `apps/dashboard` + `apps/api` | **PR 1** |
| **`apps/email-pipeline/README.md`** | Steps 2–Docker/LAN Streamlit block in Business mart section; tree comment | **Legacy** (partial label) | **Park** — move launch commands to [Legacy Streamlit](#legacy-streamlit-parked) appendix | **PR 1** |
| **`docs/RUNBOOK.md`** | Runbook map “Gmail ingest / Streamlit”; `#m-eprun-docker-streamlit`; line ~364 “internal operator tool” | Mixed | **Park** — legacy section title; map → dashboard track; fix Streamlit sentence | **PR 1** |
| **`docs/RUNBOOK.md` `#m-eprun-dashboard-optional`** | React refresh chain (active path) | **Active** (mirror sync still “parked for daily outbound”) | Keep; clarify React = product UI | **PR 1** (note only) |
| **`scripts/tools/run_streamlit_lan.sh`** | **Docs only:** `README.md`, audit docs. **Not** in tests, CI, Makefile, `.github` | **Legacy** | **Park** — file header `LEGACY`; keep script until Phase 4 | **PR 1** |
| **`Dockerfile`** | `README`, `RUNBOOK`, audits. **Not** in CI/workflows | **Legacy** | **Park** — top comment `LEGACY`; no delete yet | **PR 1** |
| **`docker-compose.yml`** | Same as Dockerfile; service `business-mart` :8501 | **Legacy** | **Park** — compose header comment; no delete yet | **PR 1** |
| **`pyproject.toml` `[dependency-groups] ui`** | CI: `.github/workflows/email-pipeline.yml`, `scripts/check-all.sh`, `CONTRIBUTING.md` | **CI-required** | **Keep** — tests import `streamlit` | — |
| **`apps/business_mart_app.py`** | Tests read source (`test_business_mart_app_ux`, etc.) | **Legacy runtime** | **Keep** — no delete | — |
| **`streamlit_*.py` modules** | `business_mart_app` imports | **Legacy runtime** | **Keep** | — |
| **`tests/test_streamlit_*.py`** | pytest + `--group ui` sync | **CI** | **Keep** | — |
| **`docs/pipeline/STREAMLIT_DATA_FRESHNESS.md`** | APP_CONTEXT, audits | **Legacy docs** | Migrate to `DATA_HEALTH.md` later | PR 2+ |
| **`docs/dataset/TATIANA_DRAFTING_COPILOT.md`** | `streamlit run` one-liner | **Legacy** | Replace with CLI/Tatiana path later | PR 2+ |
| **`docs/DEPENDENCY_GROUPS.md`** | Documents `ui` group | **Reference** | Add “legacy UI only” callout | PR 2+ |
| **`.env.example` `STREAMLIT_*`** | Env for RW flags | **Legacy ops** | Keep until RW UX elsewhere | — |
| **Root / email-pipeline `AGENTS.md`** | Already legacy/parked | **Aligned** | None | Done |
| **`ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`** | Canonical stack | **Active doc** | Link this plan | **PR 1** |

### Grep evidence — `run_streamlit_lan.sh`

```
apps/email-pipeline/README.md:225
apps/email-pipeline/docs/audits/*.md (audit cross-refs only)
```

**No** matches in `tests/`, `scripts/` (except self), `.github/`, `Makefile`, `apps/api`, `apps/dashboard`.

**Conclusion:** Safe to mark legacy in PR 1; **delete script in PR 3+** after README/RUNBOOK no longer link to it.

### Grep evidence — Docker / compose

```
apps/email-pipeline/README.md, docs/RUNBOOK.md, Dockerfile, docker-compose.yml, audits
```

**No** `.github/workflows` references to `8501`, `business-mart`, or `docker-compose.yml` (email-pipeline CI runs `pytest` only).

**Conclusion:** No active deployment path in CI. Safe to label **legacy** in PR 1; **remove Dockerfile/compose in PR 4** when operators confirm no Docker Streamlit deploys.

### Grep evidence — `--group ui`

Required by:

- `.github/workflows/email-pipeline.yml` — `uv sync --group dev --group ui --group postgres --group lab`
- `tests/test_streamlit_*`, `test_business_mart_app_*` (import streamlit or app source)

**Conclusion:** Do **not** remove `ui` group in PR 1.

---

## PR 1 — safest changes (this batch)

| Change | Risk |
|--------|------|
| New doc: this file | None |
| Root `README.md`: active stack demo; drop Streamlit badge/quick start | None |
| `apps/email-pipeline/README.md`: Streamlit launch out of primary mart flow | None |
| `docs/RUNBOOK.md`: runbook map + legacy Docker section banner + Streamlit sentence fix | None |
| `run_streamlit_lan.sh`, `Dockerfile`, `docker-compose.yml`: `LEGACY` comments only | None |
| Link from `ACTIVE_STACK_*` plan | None |

**Explicitly not in PR 1:** delete any file; change `pyproject.toml`; change CI sync groups; touch Python modules.

---

## PR 2+ — follow-ups

| PR | Work |
|----|------|
| **2** | `DEPENDENCY_GROUPS.md`, `TATIANA_DRAFTING_COPILOT.md`, `STREAMLIT_DATA_FRESHNESS.md` → legacy pointers |
| **3** | Delete `run_streamlit_lan.sh` if no operator objection |
| **4** | Remove `Dockerfile` + `docker-compose.yml` (or move to `legacy/docker/`) |
| **5** | Drop `--group ui` from CI after Streamlit tests retired |

---

## Non-goals

- No Gmail / Postgres sync / send / mirror / `--apply` behavior changes.
- No deletion of `business_mart_app.py` or `streamlit_*` modules.
- No test removals in PR 1.

---

## Verification

```bash
cd apps/email-pipeline
uv run pytest tests/test_active_stack_docs.py tests/test_module_facade_audit.py tests/test_operator_cli.py -q
uv run origenlab audit-facades -- --fail-on-manual-review
```
