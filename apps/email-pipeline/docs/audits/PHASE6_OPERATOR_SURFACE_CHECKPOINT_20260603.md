# Phase 6 — operator surface & cleanup checkpoint

Status: checkpoint (read-only summary)  
Owner: email-pipeline-maintainers  
Date: 2026-06-03  
Branch context: `docs/phase6-cleanup-checkpoint` (doc-only; no further refactor in this note)

**Purpose:** Freeze what Phase 6 (6A–6G) and prior script removals accomplished before the next cleanup lane. **No runtime behavior** was changed in the documentation / packaging / planner-only slices described here.

---

## Metrics (after Phase 5S removals + Phase 6 work)

| Measure | Value | How to reproduce |
|---------|-------|------------------|
| **Python scripts on disk** | **179** | `find scripts -name '*.py' \| wc -l` or `plan_script_consolidation.py` |
| **SCRIPT_MAP / consolidation `unknown` scripts** | **0** | `uv run python scripts/qa/plan_script_consolidation.py` → `unknown=0` |
| **Source-quality `unknown` verticals** | **192 → 102** | Compare `plan_source_quality_after_phase6e.json` vs `plan_source_quality_after_phase6f.json` (`vertical_counts.unknown`) |
| **Total scanned files (src + scripts)** | 455 | Phase 6F planner (`276` src + `179` scripts) |

Prior removals (evidence in [`PHASE2_SCRIPT_REMOVAL_EVIDENCE_20260602.md`](PHASE2_SCRIPT_REMOVAL_EVIDENCE_20260602.md)): Phase **5R** (legacy contacts QA script), Phase **5S** (three zero-ref LAB scripts). No additional script deletions in Phase 6A–6G.

---

## Preferred operator interface

**Default (Phase 6G):**

```bash
cd apps/email-pipeline
uv run origenlab --help
uv run origenlab status
uv run origenlab daily-health
uv run origenlab refresh-safety
uv run origenlab validate-csvs
uv run origenlab check-readiness
uv run origenlab post-send-digest
uv run origenlab export-dnr
uv run origenlab ndr-review
uv run origenlab audit-overlap
```

**Module fallback (same wrapper):** `uv run python -m origenlab_email_pipeline.cli <subcommand>`

**Advanced / manual fallback:** run `scripts/…` paths directly when no CLI subcommand exists or for lane-specific CLIs (ingest, campaigns, break-glass). See [`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md) and [`SCRIPT_MAP.md`](../SCRIPT_MAP.md).

Console entrypoint: `origenlab = "origenlab_email_pipeline.cli:main"` in [`pyproject.toml`](../../pyproject.toml).

---

## Phase 6 deliverables (summary)

| Phase | What shipped |
|-------|----------------|
| **6A** | [`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md) — short operator index from SCRIPT_MAP |
| **6B** | Unified CLI wrapper [`cli.py`](../../src/origenlab_email_pipeline/cli.py) (subprocess to existing scripts) |
| **6C** | Docs prefer CLI over raw `scripts/qa/…` paths |
| **6D** | Advanced CLI aliases: `export-dnr`, `ndr-review`, `audit-overlap`, `build-mart`, `gmail-ingest-help` |
| **6E** | Doc noise reduction; single “start here” command block |
| **6F** | `plan_source_quality.py` taxonomy (planner-only); `unknown` verticals 192 → 102 |
| **6G** | `uv run origenlab` console script; docs updated |

**Hard rules preserved:** no Gmail send, no Postgres migrate/`--apply`, no OPS_DAILY script moves/deletes in Phase 6; cyber/presentacion/DR50 core paths untouched.

---

## What operators should do now

1. Use **`uv run origenlab <subcommand>`** for health, safety refresh, CSV validation, post-send digest, DNR export, NDR review batches, overlap audit.
2. Use **RUNBOOK + SCRIPT_MAP** for lane work (volume/precision pipeline, ingest, campaign waves) still exposed only as `scripts/…`.
3. Treat **Postgres / Tatiana / lab** as parked or optional — [`EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md), [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md).

---

## Next possible lanes (do not start automatically)

1. **Source taxonomy round 2** — drive `plan_source_quality` `unknown` (102) lower: root `src/` modules, `scripts/qa/*` without strong keywords, `scripts/ops/*`, infrastructure scripts.
2. **Campaign-wave archive organization** — document or park `build_presentacion_*` / `build_cyber_*` as dated waves without deleting (see [`CAMPAIGN_ONEOFF_RETIREMENT_AUDIT_20260602.md`](CAMPAIGN_ONEOFF_RETIREMENT_AUDIT_20260602.md)).
3. **Postgres / migration parking** — keep verifiers and loaders behind explicit approval; align RUNBOOK with `postgres_verify` / `migration` planner buckets.
4. **Tatiana / lab optional dependency isolation** — optional-deps group boundaries per [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md); no daily-lane coupling.

**Not recommended as immediate next PR:** another script deletion batch without a fresh evidence pass (`removal_evidence.py`, ref grep, SCRIPT_MAP row).

---

## Reference artifacts

| Artifact | Path |
|----------|------|
| Script consolidation (post-5Q) | `reports/out/active/current/plan_script_consolidation_after_phase5q.json` |
| Source quality pre-6F | `reports/out/active/current/plan_source_quality_after_phase6e.json` |
| Source quality post-6F | `reports/out/active/current/plan_source_quality_after_phase6f.json` |
| Operator surface doc | [`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md) |
| Simplification audit | [`CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md) |

Regenerate planners (read-only):

```bash
cd apps/email-pipeline
uv run python scripts/qa/plan_script_consolidation.py --json-out reports/out/active/current/plan_script_consolidation_checkpoint.json
uv run python scripts/qa/plan_source_quality.py --json-out reports/out/active/current/plan_source_quality_checkpoint.json --top 50
```
