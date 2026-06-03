# Tatiana / lab boundary (OrigenLab email-pipeline)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-25

**Purpose:** Make **Tatiana**, **lab**, and **ML exploration** work **visibly** separate from **daily production** outbound and reporting—**without** moving code yet. Operator truth for paths remains [`SCRIPT_MAP.md`](SCRIPT_MAP.md), [`RUNBOOK.md`](RUNBOOK.md), and tests.

**Companion:** [`QUALITY_AND_REFACTOR_STRATEGY.md`](QUALITY_AND_REFACTOR_STRATEGY.md) (Stage **6E1** = this boundary; future **6E2** may refactor large Tatiana modules), read-only [`plan_source_quality.py`](../scripts/qa/plan_source_quality.py) (heuristic `tatiana_lab` bucket), [`ml/AI_ML_IMPLEMENTED_SUMMARY.md`](ml/AI_ML_IMPLEMENTED_SUMMARY.md).

---

## 1. What Tatiana / lab is for

- **Human-in-the-loop drafting and pilots** (Tatiana copilot, commercial drafting experiments, cohort review helpers).
- **Exploratory ML** (embeddings, clusters, ad-hoc analysis) under `scripts/ml/`.
- **Dataset and cohort exports** for evaluation and research under `scripts/dataset/`.
- **Optional OpenAI (or other LLM) calls** for **suggestions and drafts** when an operator **explicitly** runs a tool with the right keys and intent—not as a background side effect of daily sends.

---

## 2. What it is not for

- **Not** the two **daily outbound lanes** (volume / precision) described in the runbook and `SCRIPT_MAP.md`.
- **Not** a substitute for **Gmail Sent** truth, **export gate** policy, or **`outreach_contact_state`** for production memory.
- **Not** automatic production email **sending**; production send paths live under ops/daily and break-glass senders, not under `scripts/tatiana/`.
- **Not** a reason to **skip** `validate_campaign_csvs`, gate checks, or readiness scripts for real campaign work.

---

## 3. Relationship to daily outbound lanes

- **Outbound** uses **SQLite** (including **Gmail Sent** in `emails`), **`candidate_export_gate`**, CSV contracts, and operator scripts in `scripts/leads/`, `scripts/qa/`, `scripts/ingest/`, etc.
- **Tatiana / lab** may **read** the same database or exports for **analysis or drafting**, but **lab outputs** are **not** treated as **canonical** for send eligibility unless explicitly promoted into the **precision** or **volume** workflows with full review.
- **Do not** drop Tatiana-generated CSVs or drafts into `reports/out/active/current/` as if they were **reviewed** campaign inputs without a deliberate operator step (see safety below).

---

## 4. Code and script layout (map)

| Location | Role |
|----------|------|
| `src/origenlab_email_pipeline/tatiana_copilot/` | Copilot / drafting / OpenAI chat generation (e.g. `openai_chat_generator.py` — **large**; treat as **lab**). |
| `src/origenlab_email_pipeline/tatiana_review_cohort.py` | Cohort review helpers. |
| `src/origenlab_email_pipeline/tatiana_voice_cohort.py` | Voice cohort utilities. |
| `scripts/tatiana/` | Tatiana pilot and batch **entrypoints** (operator + API keys as documented per script). |
| `scripts/dataset/` | Dataset exports, pilot workflows, Tatiana-related cohort scripts. |
| `scripts/ml/` | ML exploration (clusters, embeddings) — **not** the business mart or daily pack pipeline. |
| `reports/out/*tatiana*` (and similar) | **Generated** or ad-hoc **evidence** under the general `reports/out` rules: classify with [`plan_reports_out_cleanup.py`](../scripts/qa/plan_reports_out_cleanup.py); use the **read-only** planner before cleanup; the **archiver** is **dry-run** by default ([`archive_reports_out_generated.py`](../scripts/tools/archive_reports_out_generated.py), `--apply` + `--archive-slug` to move only). |

**Root `tatiana_*.py` modules** in `src/origenlab_email_pipeline/` are part of the same **lab/Tatiana** family for ownership and refactors, even if only one file is touched in a given PR.

---

## 5. OpenAI and secrets

- **Install:** `uv sync --group lab` (OpenAI SDK is **not** in default `uv sync`; see [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md)). For all install profiles, see [`DEPENDENCY_GROUPS.md`](DEPENDENCY_GROUPS.md).
- **Expect** `OPENAI_API_KEY` (or script-specific env) only where the script documentation says so—**never** commit keys or log them.
- Use **env redaction** patterns from [`core/safety.py`](../src/origenlab_email_pipeline/core/safety.py) for any new script logging.
- **Do not** invoke OpenAI (or other paid APIs) from **import side effects** or from **tests** in CI without explicit, isolated mocks; production tests stay read-only for Tatiana as for other verticals.

---

## 6. Generated outputs and `reports/out`

- Lab runs often write under **`reports/out/`** (including paths containing **`tatiana`**, **`ml`**, **`tmp`**, or pilots). Those paths are still subject to the **non-commit**, **classify-then-maybe-move** policy in [`CRUD_SAFETY.md`](CRUD_SAFETY.md) and [`../reports/out/README.md`](../reports/out/README.md).
- Prefer **timestamped** or **subfolder** layout over piling new **loose** files at the `reports/out` root (planner calls out `loose_root_files` and large files).

---

## 7. Safety rules (summary)

1. **Not daily production:** do not run Tatiana/lab tools as a substitute for the **documented** daily outbound or ingest procedures.
2. **No surprise OpenAI:** do not add background LLM calls; only **explicit** operator-driven commands with documented env.
3. **Do not mix** Tatiana or ML **generated** outputs into `active/current/` **unless** deliberately reviewed and aligned with campaign contracts (CSV columns, `lead_id` rules, etc.).
4. **No automatic sending** from Tatiana or `scripts/ml/`; sending is a **separate** break-glass or ops path.
5. **Manage clutter** with **`plan_reports_out_cleanup`** and (if needed) the **archiver**—**no** default deletes; **dry-run** default for moves.

---

## 8. Stages (6E1 vs 6E2)

- **Stage 6E1 (this document):** **Boundary and classification** only; [`plan_source_quality.py`](../scripts/qa/plan_source_quality.py) should label `tatiana_copilot/`, `scripts/tatiana/`, `scripts/dataset/`, `scripts/ml/`, and key filenames for planning dashboards.
- **Stage 6E2 (future):** optional **refactors** of large modules (e.g. splitting `openai_chat_generator.py`) with **tests** and **no** runtime behavior change in the same change set as structure moves—**not** part of 6E1.

---

## 9. Related reading

- [`dataset/TATIANA_DRAFTING_COPILOT.md`](dataset/TATIANA_DRAFTING_COPILOT.md) · [`dataset/TATIANA_PILOT_WORKFLOW.md`](dataset/TATIANA_PILOT_WORKFLOW.md)  
- [`SCRIPT_MAP.md`](SCRIPT_MAP.md) — **Lab** bucket vs **OPS_DAILY**  
- [`QUALITY_AND_REFACTOR_STRATEGY.md`](QUALITY_AND_REFACTOR_STRATEGY.md) §4.C
