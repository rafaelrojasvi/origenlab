# Phase 8F — backend-engineering reduction audit (read-only)

Status: audit (planning only)  
Owner: email-pipeline-maintainers  
Date: 2026-06-03  
Branch context: **`main`** @ `c8a22bd` (Phases 8A–8E merged)

**Purpose:** Identify **safe** ways to reduce backend-engineering surface (install weight, optional lanes, CI scope, doc clarity) **without** deleting/moving code or changing daily operator behavior.

**Constraints (this audit):** no file moves/deletes/refactors; no Gmail/Postgres/send/purge/`--apply`; no `refresh-dashboard --apply`; do not touch `dashboard_postgres_sync.py`, `core/research_automation.py`, `run_current_campaign_pipeline.py`, send/purge scripts, raw Postgres migrations, or broad NDR apply paths.

Cross-reference: Phase 8A §6 **PR F** (Tatiana/lab optional deps); [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md); [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md); [`EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md).

---

## 1. Repo state (confirmed 2026-06-03)

```bash
git status --short
# (clean working tree)

git branch --show-current
# main

git log --oneline -5
# c8a22bd refactor(email-pipeline): reuse step runner for gmail and mirror cli (#55)
# e4830f6 refactor(email-pipeline): extract refresh step runner (#54)
# b11eeb2 docs(email-pipeline): audit runner duplication (#53)
# 6457d63 refactor(email-pipeline): improve source taxonomy round two (#52)
# 445fd11 refactor(email-pipeline): split operator cli modules (#51)
```

**Recent Phase 8 delta:** operator CLI split (8B), source taxonomy (8C), runner duplication audit (8D), shared `core.step_runner` wired to refresh/gmail/mirror (8E).

---

## 2. Executive summary

| Finding | Impact | Safe next action |
|---------|--------|------------------|
| **`openai` + `hdbscan` in default `[project.dependencies]`** | Every `uv sync` installs lab/ML packages not needed for daily SQLite outbound or `origenlab status` | Move to optional groups (`lab`, `ml`); document one-line install for Tatiana/research |
| **39 `tatiana_lab` + 3 `research_lab` + 15 `campaigns` vertical files** | Large parked/experimental code paths; easy to over-maintain | Docs + SCRIPT_MAP tags only (8A PR D); no code moves |
| **Postgres mirror lane (~17 src + 6 migrate + 5 verify scripts)** | High review burden; already EXPERIMENTAL_PARKED | Doc index + CLI cross-links only (8A PR E); **no** `dashboard_postgres_sync` refactors |
| **CI installs `dev + ui + postgres`, runs full pytest** | ~230 test files / ~40k LOC; 5 Streamlit tests need `ui` group | Optional CI matrix split (core vs ui/lab) — docs + workflow only after mapping |
| **`postgres_dashboard_api/` (~3.6k LOC) lives in email-pipeline** | Read models shared with `apps/api` (editable path dep) | **Defer** package split — API-3 already separated runtime; moving code is high risk |
| **Streamlit ~7k LOC** | Parallel UI vs React dashboard | Follow existing Streamlit retirement audit; **no delete** in 8F |
| **Operator CLI import chain is lean** | `import origenlab_email_pipeline.cli` succeeds without OpenAI/torch | Preserved after dep moves if Tatiana/research stay lazily imported |

**Verdict:** The highest **leverage / lowest risk** reduction is **dependency-group boundary work** (default install = SQLite daily ops + document parsers). Everything else in 8F should be **documentation, CI tagging, and planner visibility** — not structural refactors of mirror/research/campaign pipelines.

---

## 3. Dependency & install surface

### 3.1 Current `pyproject.toml` groups

| Group | Packages (summary) | Intended use |
|-------|-------------------|--------------|
| **(default)** | hdbscan, **openai**, orjson, pydantic, dotenv, tqdm, pymupdf, docx, openpyxl | Declared as core — but includes lab/ML libs |
| **dev** | pytest + `{ include-group = postgres }` | CI + local tests |
| **postgres** | alembic, sqlalchemy, psycopg | Mirror/migrate (parked) |
| **api** | fastapi, uvicorn | Legacy in email-pipeline; active API is `apps/api` |
| **ui** | pandas, streamlit, xlrd | Streamlit app only |
| **gmail / workspace** | google-auth, oauthlib | IMAP ingest script |
| **ml** | torch stack, sentence-transformers, faiss, sklearn, pandas | Embeddings/clusters |

**Gap:** No dedicated **`lab`** or **`tatiana`** group; OpenAI is default despite only **two** production import sites:

- `core/research_automation.py` — **top-level** `from openai import OpenAI` (loads on module import)
- `tatiana_copilot/openai_chat_generator.py` — lazy `from openai import OpenAI` inside generator method

**`hdbscan`** default dep used only in:

- `scripts/ml/email_ml_explore.py`
- `scripts/mart/build_batch_overview.py`
- `scripts/reports/build_ml_report.py`

Daily operator path (`origenlab status`, `refresh-safety`, `validate-csvs`) does **not** require openai/hdbscan/torch/streamlit/psycopg at runtime if subprocess targets existing scripts with their own deps.

### 3.2 Monorepo consumer: `apps/api`

`apps/api/pyproject.toml` depends on `origenlab-email-pipeline` (editable). Slimming default email-pipeline deps **also slims API installs** — desirable, but requires verifying `apps/api` tests still resolve imports for shared read modules (`postgres_dashboard_api`, operator reports).

### 3.3 CI (`.github/workflows/email-pipeline.yml`)

```yaml
uv sync --group dev --group data-tools --group postgres --frozen
uv run pytest
```

- Does **not** install `ml` or `gmail` groups explicitly.
- **Does** install Streamlit/pandas for ~5 tests that import `streamlit`.
- **Does** install psycopg for ~18 Postgres-related test modules.

**Reduction option:** split jobs — `pytest -m "not ui"` vs `pytest -m ui` — only after marking tests (no behavior change).

---

## 4. Code surface (planners, read-only)

Re-run (2026-06-03):

```bash
uv run python scripts/qa/plan_source_quality.py --top 30
uv run python scripts/qa/plan_script_consolidation.py
```

| Measure | Count |
|---------|------:|
| `src/**/*.py` | 285 |
| `scripts/**/*.py` | 179 |
| Scanned (src+scripts) | 464 |
| Source-quality **`unknown`** verticals | 52 |
| **`tatiana_lab`** vertical | 39 |
| **`postgres_mirror`** | 17 |
| **`postgres_api`** | 14 |
| **`campaigns`** + **`campaign_scripts`** | 15 + 6 |
| **`research_lab`** | 3 |
| **`streamlit_ui`** + **`streamlit_read`** | 3 + 2 |
| Consolidation script **`unknown`** | 0 |
| Scripts with **`--apply`** in source | 20 |
| **`break_glass`** scripts (planner) | 25 |

**Largest non-daily modules (unchanged risk list):**

| LOC | Vertical | Audit stance |
|----:|----------|--------------|
| 1683 | `research_automation.py` | **Do not touch** (8F constraint) |
| 1181 | `mart_core_postgres_migrate.py` | Parked; doc index only |
| 1048 | `dashboard_postgres_sync.py` | **Do not touch** |
| 1028 | `tatiana_copilot/openai_chat_generator.py` | Lab; optional deps only |

---

## 5. Engineering-burden hotspots

### 5.1 Tatiana / lab lane (~39 files + 9 scripts)

- Canonical boundary: [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md).
- Tests touching Tatiana/OpenAI/Streamlit drafting: **~14** modules under `tests/` (mocked; no live API in CI).
- `tatiana_copilot/generator_factory.py` **eager-imports** `openai_chat_generator` — any `import tatiana_copilot` pulls OpenAI generator module (still lazy on network call).

**Reduction (safe):** optional `lab` group + README install lines; **not** splitting `openai_chat_generator.py` yet (8A 6E2 deferred).

### 5.2 ML exploration (`scripts/ml/`, `ml` group)

- Torch/CUDA index already isolated to `--group ml`.
- **`hdbscan` incorrectly in default deps** — should align with `ml` group only.

### 5.3 Postgres parked stack

- Mirror sync, migrate loaders, Alembic, verify scripts — **EXPERIMENTAL_PARKED**.
- Operator CLI **`mirror-dashboard`** / **`refresh-dashboard`** wrap sync script; preflight env gate only in `operator_cli/mirror.py`.
- **`postgres_dashboard_api/`** (~14 modules, schemas.py 725 LOC) — read SQL for mirror reporting; consumed by **`apps/api`** mirror routes.

**Reduction (safe):** OPERATOR_COMMAND_SURFACE + SCRIPT_MAP index for migrate/verify/sync (8A PR E); **no** loader/orchestrator code changes.

### 5.4 Streamlit vs React dashboard

- [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md): **cannot remove safely today** (~7k LOC; SQLite sidecar writes + Tatiana borrador export still Streamlit-only).
- `ui` group already isolates Streamlit from default sync.

**Reduction (safe):** mark Streamlit paths **legacy supporting UI** in OPERATOR_COMMAND_SURFACE; continue React/API as primary read path.

### 5.5 Campaign wave scripts (`build_cyber_*`, `build_presentacion_*`, `src/campaigns/*`)

- Dated OPS_MAINT waves; not daily CLI.
- 8A **PR D** — SCRIPT_MAP + docs tags only.

### 5.6 Test surface

| Bucket | Test files (approx.) |
|--------|---------------------:|
| Total `tests/test_*.py` | 230 |
| Postgres-related | 18 |
| Tatiana / Streamlit / research_automation | 27 |
| Operator CLI | 3 |

Full CI pytest is the main **engineering tax** after deps. Splitting CI is optional 8F follow-up once tests are marked.

---

## 6. What NOT to touch (8F hard list)

| Path / area | Reason |
|-------------|--------|
| `dashboard_postgres_sync.py` | Complex preflight + in-process sync + watermarks |
| `core/research_automation.py` | 1683-line job pipeline; OpenAI + subprocess semantics |
| `scripts/leads/run_current_campaign_pipeline.py` | Stage machine with CSV glue |
| Send / purge scripts | Break-glass safety |
| Raw `scripts/migrate/*`, Alembic revisions | Postgres mutation policy |
| Broad NDR `--apply` paths | Operational safety |
| `refresh_outbound_safety_memory.py` step-runner adoption | Deferred per 8D audit (8D-3) |

---

## 7. Recommended safe PR sequence (8F follow-ups)

| PR | Scope | Risk | Expected reduction |
|----|-------|------|-------------------|
| **8F-1** | Move **`openai`** from default deps → new **`lab`** group; update README, REPRODUCIBILITY, TATIANA_LAB_BOUNDARY install lines; CI adds `--group lab` | Low | Smaller default/editable install; clearer “daily vs lab” |
| **8F-2** | Move **`hdbscan`** default → **`ml`** group only; update 3 script docstrings + README | Low | Default sync no longer pulls clustering lib |
| **8F-3** | Add **`docs/DEPENDENCY_GROUPS.md`** — matrix: daily ops / gmail ingest / postgres mirror / ui / ml / lab / dev | None | Onboarding + agent clarity |
| **8F-4** | SCRIPT_MAP + docs tags for **campaign wave** scripts (8A PR D) | None | Less accidental maintenance of dated waves |
| **8F-5** | Postgres **migrate + verify + sync** doc index in OPERATOR_COMMAND_SURFACE (8A PR E) | None | Single navigation for parked lane |
| **8F-6** (optional) | CI: `core` job (`uv sync --group dev --group lab --frozen`) vs `ui-postgres` job | Medium | Faster PR signal; needs pytest markers |
| **8F-7** (defer) | Lazy-import OpenAI in `research_automation.py` | Medium | Requires careful test of import side effects |
| **8F-8** (defer) | Streamlit retirement phases | High | Per Streamlit audit parity checklist |
| **8F-9** (defer) | Move `postgres_dashboard_api` toward `apps/api` | High | Cross-package import churn |

**Explicitly out of scope for 8F:** script deletes, directory reshuffles, mirror/send behavior changes, `refresh-dashboard --apply` automation.

### Phase 8F implementation status (2026-06-03)

| PR | Status | Deliverable |
|----|--------|-------------|
| **8F-1** | Done | `openai` → `lab` group; CI `--group lab`; `tests/test_lab_dependencies.py` |
| **8F-2** | Done | `hdbscan` → `ml` group; `tests/test_ml_dependencies.py` |
| **8F-3** | Done | [`docs/DEPENDENCY_GROUPS.md`](../DEPENDENCY_GROUPS.md) — canonical install matrix after 8F-1/8F-2 |

---

## 8. Operator CLI — daily path stays minimal

Verified read-only:

```bash
uv run python -c "import origenlab_email_pipeline.cli; print('cli import ok')"
# cli import ok
```

`operator_cli/*` imports: `step_runner`, `constants`, `paths`, `subprocess`, `os` — **no** OpenAI, psycopg, streamlit, or research_automation in the CLI package graph.

Daily commands (plan-only where noted):

```bash
uv run origenlab refresh-dashboard    # plan only
uv run origenlab status
uv run origenlab refresh-safety
```

---

## 9. Verification (this audit)

Read-only commands executed:

```bash
git status --short && git branch --show-current && git log --oneline -5
uv run python scripts/qa/plan_source_quality.py --top 30
uv run python scripts/qa/plan_script_consolidation.py
uv run python -c "import origenlab_email_pipeline.cli; print('cli import ok')"
rg -l 'import openai|from openai' --glob '*.py'
rg -l 'hdbscan' --glob '*.py'
```

**Not executed:** Gmail ingest, Postgres sync/migrate, send, purge, `refresh-dashboard --apply`, or any mutating operator workflow.

**Last known green operator tests (Phase 8E, main):**

```bash
uv run pytest tests/test_operator_cli.py tests/test_operator_entrypoint_contracts.py tests/test_step_runner.py -q
# 78 passed
```

---

## 10. Phase 8 series status

| Phase | Status | Notes |
|-------|--------|-------|
| 8A | Done | Tree cleanup audit |
| 8B | Done | Operator CLI package split |
| 8C | Done | Source taxonomy 102→51 unknown |
| 8D | Done | Runner duplication audit |
| 8E | Done | `core.step_runner` → refresh, gmail, mirror |
| **8F** | In progress | 8F-1…8F-3 done (deps + install guide); 8F-4…8F-5 docs-only follow-ups remain |
