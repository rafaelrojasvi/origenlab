# Campaign / date-specific one-off retirement audit — Phase 5J

**Status:** read-only audit (no code changes)  
**Date:** 2026-06-02  
**Scope:** `src/origenlab_email_pipeline/campaigns/`, campaign-related `scripts/qa/*`, tests, live docs (`SCRIPT_MAP.md`, `POST_SEND_SAFE_LOOP.md`, etc.). `reports/out/**` cited only as doc/examples where referenced from markdown — not generated data review.  
**Authority:** [`SCRIPT_MAP.md`](../SCRIPT_MAP.md), [`POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md), [`CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md)

**Related prior removals:** Phase **5A** removed `run_post_send_2026_06_01_refresh.sh` and `run_manual_outreach_2026_06_01_post_send_refresh.sh` (dated shell orchestrators).

---

## Executive summary

The `campaigns/` package mixes **three distinct layers**:

| Layer | Examples | Phase 5J verdict |
|-------|----------|------------------|
| **Reusable campaign builders** | `cyber_*`, `presentacion_origenlab_*` | **Keep (A)** — dated slugs in constants, but tested library + SCRIPT_MAP OPS_MAINT scripts |
| **Generic post-send reporting** | `post_send_digest.py`, `build_post_send_digest.py` | **Keep (D)** — wired into `POST_SEND_SAFE_LOOP`, `daily_health_report`; still has hardcoded `REPORT_DATE = "2026-06-01"` |
| **2026-06-01 wave one-offs** | `manual_outreach_2026_06_01.py`, dated digest + corrections scripts | **Removal candidate (C)** — registry of fixed recipients; wave-specific break-glass |

**Phase 5J recommendation:** **Do not delete anything in Phase 5J.** The only **grouped removal with strong evidence** is **Phase 5K batch K1** (2026-06-01 registry + dated scripts), after a small **FailureType decouple** prep step.

**Do not batch-remove** cyber or presentacion modules: they have **~3–7 dedicated test files each**, cross-imports (`presentacion` → `cyber_campaign_gate`), and `lead_research/presentacion_prospectos_merge.py` dependency.

---

## Classification legend

| Code | Meaning |
|------|---------|
| **A** | Active campaign framework (reusable builders, tests, SCRIPT_MAP entry) |
| **B** | Historical one-off but still referenced by tests/docs/evidence |
| **C** | Safe removal candidate (wave complete; replacement workflow exists) |
| **D** | Keep — safety-critical or canonical operator workflow |

---

## Summary table — modules and scripts

| Asset | LOC | Py refs | Doc refs | Class | Keep / remove | Replacement / workflow |
|-------|-----|---------|----------|-------|---------------|------------------------|
| `campaigns/manual_outreach_2026_06_01.py` | 165 | 6 | 8+ | **B → C** | **Remove in 5K** | Generic `build_post_send_digest.py` + SQLite truth |
| `campaigns/manual_outreach_failure_types.py` | 52 | 3 | 1 | **D** | **Keep** | Move `FailureType` here in 5K prep; used by `post_send_digest` |
| `campaigns/post_send_digest.py` | 532 | 2 (+ health) | 5+ | **D** | **Keep** | `scripts/qa/build_post_send_digest.py`; parameterize `REPORT_DATE` later |
| `scripts/qa/build_post_send_digest.py` | 63 | 1 | 5 | **D** | **Keep** | Step 7 in [`POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md) |
| `scripts/qa/build_manual_outreach_2026_06_01_digest.py` | 432 | 1 | 3 | **B → C** | **Remove in 5K** | `build_post_send_digest.py` |
| `scripts/qa/apply_manual_outreach_2026_06_01_corrections.py` | 156 | 1 | 3 | **B → C** | **Remove in 5K** | Targeted suppressions via `add_manual_contact_suppressions.py` / operator tools if ever needed again |
| `campaigns/cyber_outreach_campaign.py` | 691 | 6 | 4 | **A** | **Keep** | `build_cyber_outreach_campaign.py` |
| `campaigns/cyber_campaign_gate.py` | 80 | 3 | 0 | **A** | **Keep** | Shared by cyber + presentacion builders |
| `campaigns/cyber_campaign_templates.py` | 169 | 3 | 0 | **A** | **Keep** | |
| `campaigns/cyber_campaign_types.py` | 64 | 7 | 0 | **A** | **Keep** | Exported via `campaigns/__init__.py` |
| `campaigns/cyber_campaign_quality.py` | 669 | 3 | 1 | **A** | **Keep** | |
| `campaigns/cyber_campaign_context_audit.py` | 676 | 3 | 3 | **A** | **Keep** | `build_cyber_campaign_context_audit.py` |
| `scripts/qa/build_cyber_outreach_campaign.py` | 109 | 6 | 3 | **A** | **Keep** | SCRIPT_MAP OPS_MAINT |
| `scripts/qa/build_cyber_campaign_context_audit.py` | 85 | 1 | 2 | **A** | **Keep** | Depends on cyber CSV outputs |
| `campaigns/presentacion_origenlab_campaign.py` | 646 | 5 | 0 | **A** | **Keep** | `build_presentacion_origenlab_review.py`; used by `presentacion_prospectos_merge` |
| `campaigns/presentacion_origenlab_quality.py` | 785 | 5 | 1 | **A** | **Keep** | Quality pass after review CSVs |
| `campaigns/presentacion_origenlab_presend_audit.py` | 632 | 2 | 0 | **A** | **Keep** | `build_presentacion_batch1_presend_audit.py` |
| `campaigns/presentacion_origenlab_templates.py` | 175 | 5 | 0 | **A** | **Keep** | |
| `campaigns/presentacion_origenlab_types.py` | 64 | 3 | 0 | **A** | **Keep** | |
| `campaigns/presentacion_origenlab_quality_types.py` | 152 | 4 | 0 | **A** | **Keep** | |
| `scripts/qa/build_presentacion_origenlab_review.py` | 105 | 4 | 1 | **A** | **Keep** | |
| `scripts/qa/build_presentacion_origenlab_quality.py` | 75 | 1 | 1 | **A** | **Keep** | |
| `scripts/qa/build_presentacion_batch1_presend_audit.py` | 77 | 1 | 1 | **A** | **Keep** | |
| `scripts/qa/build_presentacion_prospectos_merge.py` | 56 | 2 | 2 | **A** | **Keep** | Lead-research overlay |
| `lead_research/presentacion_prospectos_merge.py` | (module) | 2 | 2 | **A** | **Keep** | Imports `presentacion_origenlab_campaign` |

**Reference counting:** `.py` / `.md` / `.sh` under `apps/email-pipeline` (excluding non-markdown under `reports/out/`). Counts are **unique files** matching symbol/path patterns (2026-06-02).

---

## Deep dive — 2026-06-01 manual outreach cluster

### `manual_outreach_2026_06_01.py`

**What it is:** Frozen registry (`MANUAL_PROSPECT_ROWS`, `CYBER_BCC_RECIPIENTS`, etc.) for the **2026-06-01** manual prospect + Cyber BCC wave. Docstring: *"Registry for manual prospect outreach + Cyber BCC extra (2026-06-01)"*.

**Python importers (6):**

- `campaigns/manual_outreach_failure_types.py` — imports `FailureType` only
- `scripts/qa/build_manual_outreach_2026_06_01_digest.py` — primary consumer
- `scripts/qa/apply_manual_outreach_2026_06_01_corrections.py` — string constant `UPDATED_BY` only
- `tests/test_manual_outreach_2026_06_01.py`

**Classification:** **B** today (tests + dated digest script); **C** after wave closed — **no production path** except the dated digest script.

### `manual_outreach_failure_types.py`

**What it is:** NDR note → `failure_type` label mapping (`classify_failure_type`).

**Python importers (3):**

- `campaigns/post_send_digest.py` — **generic post-send digest (D)**
- `scripts/qa/build_manual_outreach_2026_06_01_digest.py`
- `tests/test_manual_outreach_2026_06_01.py`

**Blocker for removing registry:** `FailureType` Literal is defined in `manual_outreach_2026_06_01.py`. **5K prep:** move `FailureType` into this module (or neutral `ndr_failure_types.py`).

**Classification:** **D — keep** (feeds canonical post-send digest).

### `post_send_digest.py` + `build_post_send_digest.py`

**What it is:** Read-only Gmail SQLite digest (CSV/MD/JSON) for post-send operator review.

**Wiring:**

- [`POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md) step 7
- [`CURRENT_SAFETY_CHECKPOINT.md`](../pipeline/CURRENT_SAFETY_CHECKPOINT.md)
- `qa/daily_health_report.py` → `inspect_latest_post_send_digest`
- `tests/test_daily_health_report.py` mocks `build_post_send_digest`

**Caveat:** `REPORT_DATE = "2026-06-01"` is hardcoded (lines 22, 400, 456). CLI accepts `--since-days` but report metadata still uses fixed date. **Not a removal candidate** — needs **refactor** (future PR), not deletion.

**Classification:** **D**

### Dated scripts (5K candidates)

| Script | Purpose | Mutates SQLite | Class |
|--------|---------|----------------|-------|
| `build_manual_outreach_2026_06_01_digest.py` | Wave-specific digest duplicating much of `post_send_digest` logic inline | No | **C** |
| `apply_manual_outreach_2026_06_01_corrections.py` | Fix hannelore / mle / dfuente rows from 2026-06-01 NDR confusion | **Yes (`--apply`)** | **C** (break-glass already applied) |

**Replacement workflow:**

1. Post-send analysis → `uv run python scripts/qa/build_post_send_digest.py --since-days N`
2. Full loop → [`POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md)
3. Ad-hoc suppressions → documented break-glass tools (`add_manual_contact_suppressions.py`, NDR allowlist scripts) — **not** a dated corrections script

---

## Deep dive — Cyber campaign cluster

**Package surface:** `campaigns/__init__.py` exports `build_cyber_outreach_campaign`, `write_cyber_campaign_outputs`, `CYBER_CAMPAIGN_SLUG`, `CyberCampaignRow`.

**Internal graph:**

```
cyber_campaign_types
    ← cyber_campaign_gate, cyber_campaign_templates
    ← cyber_campaign_quality
    ← cyber_outreach_campaign (builder)
    ← cyber_campaign_context_audit (evidence report)
presentacion_origenlab_campaign → cyber_campaign_gate.product_angle  (cross-campaign reuse)
```

**Tests (3 files, ~15+ cases):**

- `tests/test_cyber_outreach_campaign.py`
- `tests/test_cyber_campaign_quality.py`
- `tests/test_cyber_campaign_context_audit.py`

**Classification:** **A** — campaign slug `cyber_lab_equipment_cl_2026` is dated, but the module set is a **reusable read-only builder + gate + audit framework**. SCRIPT_MAP lists as **OPS_MAINT**, not LEGACY_DO_NOT_USE.

**Phase 5 removal:** **Not recommended.**

---

## Deep dive — Presentación OrigenLab cluster

**Campaign slug:** `presentacion_origenlab_cyber_suave_2026` (`presentacion_origenlab_types.py`).

**Script chain (SCRIPT_MAP OPS_MAINT):**

1. `build_presentacion_origenlab_review.py` → review CSVs + messages MD
2. `build_presentacion_origenlab_quality.py` → quality scoring (requires step 1)
3. `build_presentacion_batch1_presend_audit.py` → pre-send audit
4. `build_presentacion_prospectos_merge.py` → merge with lead-research overlay

**Cross-package dependency:**

- `lead_research/presentacion_prospectos_merge.py` imports `presentacion_origenlab_campaign` (`BATCH_KEY_PRESENTACION = "presentacion_origenlab_2026"`)

**Tests (4 files):**

- `tests/test_presentacion_origenlab_campaign.py`
- `tests/test_presentacion_origenlab_quality.py`
- `tests/test_presentacion_origenlab_presend_audit.py`
- `tests/test_presentacion_prospectos_merge.py`

**Classification:** **A** — same pattern as cyber (dated slug, reusable builder). **Not a safe Phase 5 batch.**

---

## Grouped removal candidates (Phase 5K only)

Strong evidence supports **one batch**:

### Batch K1 — 2026-06-01 manual wave artifacts

| Delete | Reason |
|--------|--------|
| `src/.../campaigns/manual_outreach_2026_06_01.py` | Frozen recipient registry; no generic operator use |
| `scripts/qa/build_manual_outreach_2026_06_01_digest.py` | Superseded by `build_post_send_digest.py` |
| `scripts/qa/apply_manual_outreach_2026_06_01_corrections.py` | Break-glass for 3 emails; one-time wave |

| Keep / refactor in same PR | Reason |
|---------------------------|--------|
| `campaigns/manual_outreach_failure_types.py` | Used by `post_send_digest` |
| `campaigns/post_send_digest.py` | POST_SEND_SAFE_LOOP |
| All `cyber_*` and `presentacion_*` | Active framework (A) |

**5K prep (required before delete):**

1. Move `FailureType` Literal from `manual_outreach_2026_06_01.py` into `manual_outreach_failure_types.py` (no behavior change).
2. Update `tests/test_manual_outreach_2026_06_01.py` → rename to `tests/test_manual_outreach_failure_types.py` (or merge failure-type tests into post-send digest tests).

**5K docs to update:**

- `docs/SCRIPT_MAP.md` — remove dated script rows; point to generic digest
- `docs/audits/CODEBASE_SIMPLIFICATION_AUDIT_20260602.md` — mark gap closed
- `tests/removal_evidence.py` — add `REMOVED_PHASE5K_TARGETS` (optional, consistent with 5A–5I)

**Not in K1:** cyber, presentacion, `post_send_digest`, `build_post_send_digest.py`.

---

## Explicit non-candidates

| Asset | Why **D** / defer |
|-------|-------------------|
| `post_send_digest.py` | Canonical post-send read-only reporting; daily health inspect |
| `build_post_send_digest.py` | POST_SEND_SAFE_LOOP step 7 |
| `manual_outreach_failure_types.py` | Shared NDR label helper for digest |
| All `cyber_*` modules + scripts | Tested framework; presentacion reuse |
| All `presentacion_*` modules + scripts | Tested framework; lead_research merge |
| `campaigns/__init__.py` | Public cyber API surface |

---

## Tests to update (Phase 5K)

| Current test | Action in 5K |
|--------------|--------------|
| `tests/test_manual_outreach_2026_06_01.py` | Remove registry tests; keep / move `classify_failure_type` tests |
| `tests/test_daily_health_report.py` | No change (uses `post_send_digest`, not registry) |
| `tests/test_commercial_intel_*` | No change |
| `tests/test_cyber_*.py` | No change |
| `tests/test_presentacion_*.py` | No change |
| `tests/test_run_current_campaign_pipeline.py` | No change (precision lane orchestrator, separate from QA campaign builders) |

**5K pytest command:**

```bash
cd apps/email-pipeline

uv run pytest \
  tests/test_manual_outreach_failure_types.py \
  tests/test_daily_health_report.py \
  tests/test_script_removal_evidence.py \
  -q

# Regression — post-send + campaign frameworks untouched
uv run pytest \
  tests/test_cyber_outreach_campaign.py \
  tests/test_cyber_campaign_quality.py \
  tests/test_cyber_campaign_context_audit.py \
  tests/test_presentacion_origenlab_campaign.py \
  tests/test_presentacion_origenlab_quality.py \
  tests/test_presentacion_origenlab_presend_audit.py \
  tests/test_presentacion_prospectos_merge.py \
  -q
```

(Add a small `tests/test_post_send_digest.py` if none exists after 5K — today digest behavior is only covered via `test_daily_health_report` mock path.)

---

## Suggested PR sequence

| PR | Scope | Risk |
|----|-------|------|
| **5J (this audit)** | Doc only | None |
| **5K1 — prep** | Move `FailureType` to `manual_outreach_failure_types.py`; rename/split tests; no deletions | Low |
| **5K2 — delete wave artifacts** | Delete registry module + 2 dated scripts; update SCRIPT_MAP + removal evidence; grep proof | Low |
| **5L (future, optional)** | Parameterize `REPORT_DATE` in `post_send_digest.py` from CLI | Low |
| **6+ (future)** | New campaign year: copy cyber/presentacion pattern with new slug constants — **do not delete** old builders until operator sign-off | Medium |

**Do not combine 5K2 with cyber/presentacion deletion** — evidence does not support it.

---

## Appendix — `rg` commands (repeat audit)

```bash
cd apps/email-pipeline

# 2026-06-01 cluster
rg 'manual_outreach_2026_06_01' --glob '*.py' --glob '*.md'
rg 'build_manual_outreach_2026_06_01_digest|apply_manual_outreach_2026_06_01_corrections'

# Generic post-send (keep)
rg 'post_send_digest|build_post_send_digest' --glob '*.py' --glob '*.md'

# Cyber / presentacion frameworks (keep)
rg 'cyber_outreach_campaign|cyber_campaign_' --glob '*.py' | head
rg 'presentacion_origenlab' --glob '*.py' | head

# Cross dependency
rg 'presentacion_prospectos_merge|cyber_campaign_gate' src/
```

---

## Handoff

| Item | Result |
|------|--------|
| **Files changed** | `docs/audits/CAMPAIGN_ONEOFF_RETIREMENT_AUDIT_20260602.md` (this report only) |
| **Code/tests changed** | None |
| **Phase 5J removals** | **None** |
| **Recommended Phase 5K batch** | **K1 only** — `manual_outreach_2026_06_01.py` + 2 dated scripts (after FailureType decouple) |
| **Keep** | `post_send_digest`, `manual_outreach_failure_types`, all cyber/presentacion stacks |
