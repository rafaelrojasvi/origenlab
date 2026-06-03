# Phase 8D — runner / subprocess duplication audit (read-only)

Status: audit (discovery only)  
Owner: email-pipeline-maintainers  
Date: 2026-06-03  
Branch context: after Phase **8C** (source-quality taxonomy); operator CLI split in **8B**

**Purpose:** Inventory duplicated step/subprocess orchestration patterns before extracting shared utilities. **No refactors, moves, deletes, or mutating runs** in this audit.

**Files inspected:**

| File | Role |
|------|------|
| `src/origenlab_email_pipeline/operator_cli/runner.py` | Generic subcommand subprocess dispatch |
| `src/origenlab_email_pipeline/operator_cli/gmail.py` | INBOX + Sent ingest chain |
| `src/origenlab_email_pipeline/operator_cli/mirror.py` | Postgres mirror env gate + alembic/sync chain |
| `src/origenlab_email_pipeline/operator_cli/refresh.py` | Multi-step refresh-dashboard orchestration |
| `scripts/qa/refresh_outbound_safety_memory.py` | QA export/validate chain with timing + capture |
| `scripts/leads/run_current_campaign_pipeline.py` | Campaign stage machine with CSV glue |
| `scripts/sync/sync_dashboard_postgres_mirror.py` | Thin entrypoint → `dashboard_postgres_sync.main` |
| `src/origenlab_email_pipeline/dashboard_postgres_sync.py` | Mirror preflight + loader subprocesses + in-process sync |
| `src/origenlab_email_pipeline/core/research_automation.py` | Deep research pipeline (API + subprocess mix) |

Cross-reference: Phase 8A §5–6 proposed **PR C — shared runner utilities**; this audit scopes that work.

---

## 1. Repeated patterns

### 1.1 Subprocess.run loops

| Location | Pattern | Notes |
|----------|---------|-------|
| `operator_cli/gmail.py` `run_gmail_ingest` | `for cmd in build_gmail_ingest_argv_list(...): subprocess.run(...)` | 2-step fixed chain (INBOX → Sent) |
| `operator_cli/mirror.py` `run_mirror_dashboard` | `for cmd in build_mirror_dashboard_argv_list(...): subprocess.run(...)` | Optional alembic then sync |
| `operator_cli/refresh.py` `run_refresh_dashboard` | `for step in steps: execute(step.command, ...)` | Delegates to `run_subcommand` (not raw argv loop) |
| `operator_cli/runner.py` `run_subcommand` | Single `subprocess.run` or delegate | No multi-step loop except via gmail/mirror |
| `refresh_outbound_safety_memory.py` | `for (name, cmd) in steps: _run_step(name, cmd)` | 6-step fixed chain; **capture_output=True** |
| `run_current_campaign_pipeline.py` | Repeated `_run_py(...)` per stage | 2–8 calls per stage; not one declarative list |
| `dashboard_postgres_sync.py` | `for step in steps: run_loader_subprocess(cmd, ...)` | 1–2 loader scripts; then **in-process** Python sync |
| `research_automation.py` | Inline `_run_subprocess(...)` at validation/evidence/process/coverage phases | 4 calls inside one long function |

**Common core:** build argv → `subprocess.run(..., cwd=..., check=False)` → inspect `returncode` → stop or continue.

**Divergence:**

- **Streaming vs capture:** operator CLI and `dashboard_postgres_sync` stream stdout/stderr to the terminal; `refresh_outbound_safety_memory`, `run_current_campaign_pipeline`, and `research_automation` capture output (for parsing, error display, or JSON extraction).
- **Timeout:** only campaign pipeline (`600s`) and research automation (`300s`) set `subprocess.run(..., timeout=...)`.
- **Env:** research automation injects `PYTHONPATH=<repo>/src`; others rely on `cwd` + default env.

### 1.2 Step labels / progress logging

| Location | Format | When logged |
|----------|--------|-------------|
| `refresh.py` | `[refresh-dashboard] {i}/{total} {label}` | Apply mode only; plan prints static numbered list |
| `refresh_outbound_safety_memory.py` | `[{idx}/{len(steps)}] {name}` then `-> OK/FAIL (rc=..., {elapsed}s)` | Every step |
| `dashboard_postgres_sync.py` | `[sync] loader {name}: ...` / `[sync] preflight ...` via `phase_log()` | Preflight + each loader |
| `gmail.py` / `mirror.py` | *(none)* | Silent unless child script prints |
| `run_current_campaign_pipeline.py` | Stage-specific human summaries | After CSV glue, not per subprocess |
| `research_automation.py` | `_emit_progress(phase=...)` callback | Phase names for Streamlit/job UI |

No shared prefix convention today. Closest semantic match: **refresh-dashboard apply loop** ↔ **refresh_outbound_safety_memory** (indexed steps + stop message).

### 1.3 Stop-on-first-failure behavior

| Location | Policy | Failure signal |
|----------|--------|----------------|
| `gmail.py`, `mirror.py` | Hard stop; return first non-zero rc | `return int(proc.returncode)` |
| `refresh.py` | Hard stop; stderr message with step index | `return int(rc)` |
| `refresh_outbound_safety_memory.py` | Hard stop on `hard_failed`; prints captured stdout/stderr | `break` loop; exit 1 if any hard failure |
| `run_current_campaign_pipeline.py` | Hard stop per `_run_py`; writes stderr to sys.stderr | `return run.returncode` (except send export rc `2` allowed) |
| `dashboard_postgres_sync.py` | Hard stop loaders; `raise RuntimeError(...)` | Caught by outer handler → watermark `status=error` |
| `research_automation.py` | Hard stop → `raise RuntimeError` with stdout/stderr | Exception propagates to caller |

**Soft-failure exception:** `refresh_outbound_safety_memory.py` treats `check_outbound_readiness` verdict `ready_with_warnings` as success unless `--fail-on-ready-with-warnings`. No other inspected file has equivalent post-step verdict parsing.

### 1.4 cwd / repo_root handling

| Location | Root resolution |
|----------|-----------------|
| `operator_cli/paths.py` `repo_root()` | `Path(__file__).resolve().parents[3]` → `apps/email-pipeline` |
| `refresh_outbound_safety_memory.py` | `Path(__file__).resolve().parents[2]` (same directory, duplicated formula) |
| `run_current_campaign_pipeline.py` | `_ROOT = Path(__file__).resolve().parents[2]` + `sys.path.insert` |
| `sync_dashboard_postgres_mirror.py` | `REPO = Path(__file__).resolve().parents[2]` + `sys.path.insert` |
| `dashboard_postgres_sync.py` | `root` from argparse / caller; loaders use `cwd=str(repo_root)` |
| `research_automation.py` | `app_root` parameter; `_run_subprocess(..., cwd=app_root)` |

All resolve to **`apps/email-pipeline`**, but **three independent implementations** (`operator_cli.paths.repo_root`, script `parents[2]`, research `app_root` arg). Consolidating root resolution is out of scope for step_runner but worth noting for operator_cli consumers.

### 1.5 Env preflight checks

| Location | Preflight | Fail behavior |
|----------|-----------|---------------|
| `mirror.py` | `postgres_url_configured()` over `POSTGRES_ENV_VARS` | Print `missing_postgres_env_message()`; exit **2** before any subprocess |
| `mirror.py` | `mirror_dashboard_uses_cloud_postgres_only()` → auto `--allow-non-scratch-postgres` | Flag injection only |
| `dashboard_postgres_sync.py` | psycopg import, Postgres URL resolve, alembic head, SQLite mart counts, scratch target | Structured `result` dict + errors list; no subprocess until preflight passes |
| `gmail.py` | `validate_gmail_ingest_passthrough` rejects `--replace-source` | `ValueError` before subprocess |
| Others | None at orchestration layer | Child scripts enforce their own gates |

Env preflight is **mirror-specific** in operator CLI; Postgres sync has a **much larger** preflight surface (not a simple env-var check).

### 1.6 Dry-run / apply gates

| Location | Gate | Effect |
|----------|------|--------|
| `refresh.py` | `options.apply` | `False` → print plan only, exit 0; `True` → run steps |
| `mirror.py` | `apply` | `False` → append `--dry-run` to sync argv |
| `dashboard_postgres_sync.py` | `args.dry_run` | Skip loader subprocesses; run read-only preflight + optional in-process previews |
| `run_current_campaign_pipeline.py` | `args.apply` | Import dry-run always; `--apply` adds second import subprocess |
| `refresh_outbound_safety_memory.py` | *(none)* | Always runs all export/validate steps |
| `research_automation.py` | Various flags (`run_contacted_coverage_check`, etc.) | Optional subprocess steps |

Dry-run semantics are **not uniform** (CLI wrapper dry-run vs script `--dry-run` vs plan-only orchestrator). A shared runner should **not** assume one global dry-run policy.

---

## 2. Safe candidates for shared utility extraction

**Tier 1 — low risk, high similarity (recommended first):**

| File | Why safe | Shared pieces |
|------|----------|---------------|
| `operator_cli/refresh.py` | Already uses `RefreshDashboardStep` + injectable `runner`; tests mock `run_subcommand` | Indexed progress log, stop-on-failure loop, optional plan-only mode stays local |
| `operator_cli/gmail.py` `run_gmail_ingest` | Fixed 2-step argv list; no capture; same cwd policy as refresh | Generic “run argv list sequentially” helper |
| `operator_cli/mirror.py` `run_mirror_dashboard` | Same loop shape as gmail; env preflight stays **before** shared runner | Loop only; keep `postgres_url_configured()` in mirror module |

**Tier 2 — moderate benefit, needs adapter flags:**

| File | Why moderate | Extra requirements |
|------|--------------|-------------------|
| `scripts/qa/refresh_outbound_safety_memory.py` | Clear 6-step list + progress; good second adopter | `capture_output=True`, per-step timing, **soft-failure hook** for readiness verdict |
| `operator_cli/runner.py` | Single-shot runs; less duplication than multi-step | Could call shared `run_step_once` for cwd consistency only |

**Tier 3 — defer (orchestration stays local):**

| File | Reason |
|------|--------|
| `run_current_campaign_pipeline.py` | Stage functions with CSV read/write between subprocesses; not a linear `StepSpec` list |
| `dashboard_postgres_sync.py` | Loaders are one phase; preflight, watermarks, and in-process sync dominate |
| `research_automation.py` | 1683-line pipeline; progress callbacks, API retries, special rc rules |
| `sync_dashboard_postgres_mirror.py` | 27-line shim — nothing to extract |

---

## 3. Files that should NOT be touched yet

| File | Do-not-touch rationale |
|------|------------------------|
| **`dashboard_postgres_sync.py`** | Loader subprocess loop is ~15 lines inside a 1000+ line module with SQLite/Postgres preflight, alembic head checks, watermark writes, and post-loader **in-process** sync (`sync_email_classification_canonical`, commercial deals, equipment/warm optional loaders). Extracting the loop alone adds indirection without reducing complexity. Injectable `loader_runner` already supports tests. |
| **`core/research_automation.py`** | Subprocess calls are embedded in a stateful research job (API polling, retries, `_emit_progress`, special rc `{0,1}` for evidence verify). High regression risk; Streamlit/job callers depend on exception messages and artifact paths. |
| **`run_current_campaign_pipeline.py`** | Stage machine with domain logic (overlap split, CSV writes, `--apply` import gate, send rc `2` tolerance). Not isomorphic to operator refresh workflow. |
| **`sync_dashboard_postgres_mirror.py`** | Entrypoint only. |
| **`operator_cli/parser.py` / `constants.py` / `paths.py`** | No subprocess duplication; leave stable during runner PR. |

**Conservative rule:** do not refactor **Postgres mirror write paths** or **research/lab pipelines** until operator CLI orchestration proves the shared helper in production tests.

---

## 4. Proposed minimal shared module (if justified)

**Path:** `src/origenlab_email_pipeline/core/step_runner.py`

**Scope:** orchestration primitive only — no business preflight, no dry-run policy, no Postgres/Gmail semantics.

```python
@dataclass(frozen=True)
class StepSpec:
    """One sequential step in a local subprocess workflow."""

    label: str
    argv: tuple[str, ...]  # full argv including sys.executable
    # Optional hooks added only when refresh_outbound_safety_memory adopts:
    # capture_output: bool = False
    # on_result: Callable[[CompletedProcess], StepOutcome] | None = None


def run_step_sequence(
    steps: Sequence[StepSpec],
    *,
    cwd: Path,
    log_prefix: str = "",
    stop_on_error: bool = True,
    stream_output: bool = True,
) -> int:
    """Run steps in order; return first non-zero exit or 0."""
```

**Design constraints:**

- **First consumer:** `operator_cli.refresh.run_refresh_dashboard` — keep `RefreshDashboardStep` + `run_subcommand` injection; optionally implement `run_step_sequence` for the **apply** loop logging only, or map steps to `StepSpec` where `argv` is built via `build_subcommand_argv` (refresh may keep callable runner instead of argv — see PR plan).
- **cwd:** require explicit `cwd`; operator CLI passes `repo_root()`.
- **Logging:** `{log_prefix}{i}/{total} {label}` to match refresh-dashboard today.
- **Out of scope for v1:** env preflight, dry-run gates, capture_output, timeouts, soft-failure verdict parsing, watermark side effects.

**Justification:** Three operator_cli modules (`gmail`, `mirror`, `refresh`) share the same **sequential hard-stop** pattern with only logging and pre-call hooks differing. A ~40-line module removes copy-pasted loops without forcing dashboard or research refactors.

**Not justified yet:** a heavier `OperatorRunner` class wrapping argparse, env gates, and plan/apply — that would duplicate `mirror.py` and `refresh.py` responsibilities.

---

## 5. Follow-up PR plan (exact order)

### PR 8D-1 — Introduce `core/step_runner.py` + wire `operator_cli.refresh` only

| Item | Detail |
|------|--------|
| **Add** | `step_runner.py` with `StepSpec`, `run_step_sequence()` |
| **Change** | `operator_cli/refresh.py` — apply-mode loop uses shared helper for progress + stop-on-failure |
| **Keep unchanged** | `build_refresh_dashboard_steps`, plan-only path, injectable `runner` (tests continue to mock `run_subcommand`) |
| **Tests** | Extend `tests/test_operator_cli.py`: assert log lines / exit code on mocked failure mid-sequence; unit tests for `run_step_sequence` with fake subprocess (monkeypatch `subprocess.run`) |
| **Do not change** | `gmail.py`, `mirror.py`, `runner.py` in this PR (optional follow-up 8D-2) |

### PR 8D-2 (optional) — Adopt in `gmail.py` + `mirror.py`

| Item | Detail |
|------|--------|
| **Change** | Replace inner `for cmd in ...: subprocess.run` loops with `run_step_sequence` |
| **Keep local** | `mirror.py` env preflight and argv builders; `gmail.py` passthrough validation |
| **Tests** | Existing gmail/mirror CLI tests must pass unchanged |

### PR 8D-3 (optional) — Adopt in `refresh_outbound_safety_memory.py`

| Item | Detail |
|------|--------|
| **Extend** | `StepSpec` or companion `run_step_sequence_captured()` with timing + stdout/stderr |
| **Preserve** | `ready_with_warnings` soft-success behavior and summary block |
| **Tests** | New tests in `tests/test_refresh_outbound_safety_memory.py` (or existing if present) with mocked subprocess |
| **Risk** | Medium — script is operator-facing QA chain; verify cwd explicitly (today omits `cwd=` on subprocess) |

### Explicitly excluded from 8D series

- `dashboard_postgres_sync.py` — revisit only if loader loop is isolated behind an injectable runner API redesign (separate Postgres PR E).
- `research_automation.py` — no subprocess extraction until research job API stabilizes.
- `run_current_campaign_pipeline.py` — stage orchestration stays script-local.

---

## 6. Duplication summary matrix

| Concern | refresh | gmail | mirror | safety_memory | campaign | pg_sync | research |
|---------|:-------:|:-----:|:------:|:-------------:|:--------:|:-------:|:--------:|
| Sequential subprocess loop | ✓ | ✓ | ✓ | ✓ | partial | ✓ | partial |
| Indexed progress log | ✓ | — | — | ✓ | — | ✓ | via callback |
| Stop on first hard failure | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Shared repo_root helper | ✓ | ✓ | ✓ | duplicate | duplicate | caller | arg |
| Env preflight | — | validate args | Postgres env | — | — | extensive | — |
| Dry-run / plan gate | ✓ | — | ✓ | — | partial | ✓ | flags |
| capture_output | — | — | — | ✓ | ✓ | — | ✓ |
| In-process steps after subprocess | — | — | — | — | ✓ | ✓ | ✓ |

---

## 7. Verification (this audit)

```bash
cd apps/email-pipeline
uv run pytest tests/test_operator_cli.py tests/test_operator_entrypoint_contracts.py -q
# 73 passed (2026-06-03)
```

No Gmail, Postgres writes, or `--apply` executed during this audit.
