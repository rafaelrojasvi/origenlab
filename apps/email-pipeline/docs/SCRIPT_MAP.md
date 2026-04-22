# Email pipeline — script map (outreach & campaigns)

**Purpose:** One place to see **which scripts matter day to day**, which are **audit/debug**, and which are **candidates to consolidate** later. This doc is **navigation only**; behavior lives in code and [`RUNBOOK.md`](RUNBOOK.md).

**Canonical working directory:** `apps/email-pipeline/` (`cd apps/email-pipeline`).

**Canonical campaign workspace:** fresh inputs and outputs for the two outbound lanes belong in **`reports/out/active/current/`**. Other files under `reports/out/active/` (and most of `reports/out/archive/`) are **evidence, history, or ad-hoc exports** — not the default place to pick up “today’s” CSV for DeepSearch or send lists.

**Rule:** Broad **volume marketing** rows must **not** go into **`lead_contact_research`** unless they have a real **`lead_id`**. Use **`reviewed_marketing_contacts.csv`** → **`process_broad_marketing_contacts.py`** → **`send_ready_marketing.csv`**.

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| **KEEP_CORE** | On the two daily workflows or required infrastructure (gate, state, ingest). |
| **KEEP_AUDIT** | Read-only or hygiene; use when debugging saturation, overlap, or data trust. |
| **KEEP_DEBUG** | Troubleshooting / CI / migration helpers; not daily operator path. |
| **CONSOLIDATE** | Overlaps another script’s job; safe to keep, but docs should point to one “primary” path. |
| **ARCHIVE_CANDIDATE** | Legacy or niche lane; still in repo, not part of the two-lane mental model. |

---

## Two daily workflows (commands)

### A) Volume marketing lane

1. `uv run python scripts/qa/export_do_not_repeat_master.py`
2. DeepSearch saves **`reports/out/active/current/reviewed_marketing_contacts.csv`**
3. `uv run python scripts/qa/validate_campaign_csvs.py --file reports/out/active/current/reviewed_marketing_contacts.csv --kind marketing_contacts --strict`
4. `uv run python scripts/leads/process_broad_marketing_contacts.py`
5. Review **`send_ready_marketing.csv`** (and `marketing_needs_manual_review.csv` if needed)
6. Send manually or via **`scripts/qa/send_inline_html_email_via_gmail_api.py`** (optional)
7. **`scripts/leads/mark_sent_batch_contacted.py`** + Gmail Sent ingest (`scripts/ingest/05_workspace_gmail_imap_to_sqlite.py`)

### B) Precision lead lane

1. `uv run python scripts/leads/run_current_campaign_pipeline.py --stage prepare ...`
2. DeepSearch saves **`reports/out/active/current/reviewed_deepsearch.csv`** (with **`lead_id`**)
3. `uv run python scripts/leads/run_current_campaign_pipeline.py --stage process-reviewed --apply ...`
4. Review **`send_ready.csv`**
5. `uv run python scripts/leads/run_current_campaign_pipeline.py --stage post-send ...`  
   (and/or **`mark_sent_batch_contacted.py`** + Sent ingest, per your runbook detail)

---

## Daily scripts (KEEP_CORE for operators)

| Path | Tag | Role | Typical outputs / notes |
|------|-----|------|-------------------------|
| `scripts/qa/export_do_not_repeat_master.py` | KEEP_CORE | Merge “do not repeat” emails for DeepSearch + volume processor | `reports/out/active/current/do_not_repeat_master.{csv,txt}`, `do_not_repeat_summary.json` |
| `scripts/leads/process_broad_marketing_contacts.py` | KEEP_CORE | Validate, gate, split volume contacts | `marketing_*.csv`, `send_ready_marketing.csv`, `marketing_contacts_summary.json` |
| `scripts/qa/validate_campaign_csvs.py` | KEEP_CORE | CSV contracts (`marketing_contacts`, `reviewed_deepsearch`, `send_ready`, etc.) | stdout / exit code; optional `--json-out` |
| `scripts/leads/run_current_campaign_pipeline.py` | KEEP_CORE | Orchestrates precision lane (prepare / process-reviewed / post-send) | Files under `active/current/` |
| `scripts/qa/prepare_outbound_campaign_workspace.py` | KEEP_CORE | Initializes/archives **`active/current`** + campaign manifest | Placeholder / manifest files |
| `scripts/leads/export_lead_contact_research_queue.py` | KEEP_CORE | Exports **`research_queue.csv`** for lead DeepSearch | `active/current/research_queue.csv` (when used with pipeline) |
| `scripts/leads/import_lead_contact_research_csv.py` | KEEP_CORE | Applies reviewed DeepSearch into **`lead_contact_research`** | DB writes (precision lane only) |
| `scripts/leads/export_next_marketing_recipients.py` | KEEP_CORE | **`send_ready.csv`** from `lead_master` + shared gate | Lead send list |
| `scripts/leads/mark_sent_batch_contacted.py` | KEEP_CORE | Post-send **`outreach_contact_state`** updates | Sidecar only |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | KEEP_CORE | Gmail → **`emails`** (Sent / inbox) | Required for Sent-history truth |
| `scripts/qa/send_inline_html_email_via_gmail_api.py` | KEEP_CORE | Optional Gmail API send (not auto-run) | Operator-invoked |

**Core modules (not scripts):** `src/origenlab_email_pipeline/candidate_export_gate.py`, `marketing_export_context.py`, `outbound_core.py`, `outreach_contact_state.py`, `next_marketing_queue.py`, `csv_contracts.py`, `outbound_sent_preflight.py` — **KEEP_CORE** infrastructure.

---

## Debug / audit scripts (KEEP_AUDIT / KEEP_DEBUG)

| Path | Tag | Role |
|------|-----|------|
| `scripts/qa/export_contacted_lead_overlap_audit.py` | KEEP_AUDIT | Pre-import / pre-send overlap vs Sent, state, suppressions, lead/research |
| `scripts/qa/export_gate_audit_csv.py` | KEEP_AUDIT | Per-candidate gate flags for lead (or archive) lane |
| `scripts/qa/export_outreach_volume_rollup.py` | KEEP_AUDIT | Saturation metrics rollup (counts by source) |
| `scripts/qa/export_supplier_domain_false_positive_audit.py` | KEEP_AUDIT | Supplier domain vs institutional false-positive hints |
| `scripts/qa/check_outbound_readiness.py` | KEEP_AUDIT | Readiness / config checks |
| `scripts/leads/approve_reviewed_deepsearch_rows.py` | KEEP_AUDIT | Promote manual-review rows to import (precision lane helper) |
| `scripts/leads/backfill_contacted_from_gmail_sent.py` | KEEP_AUDIT | Backfill **`outreach_contact_state`** from Sent (dry-run default) |
| `scripts/qa/print_outbound_run_summary.py` | KEEP_DEBUG | Pretty-print outbound summary JSON |
| `scripts/qa/export_candidate_audit.py` | KEEP_DEBUG | Sample rows through gate (informational) |
| `scripts/qa/validate_sqlite_archive_for_postgres.py` | KEEP_DEBUG | Migration / validation |
| `scripts/qa/publish_gate.py` | KEEP_DEBUG | Publication / trust gate (broader than outbound) |

**Overlap note:** **`export_do_not_repeat_master.py`** (operator *input list*) vs **`export_outreach_volume_rollup.py`** (*metrics*). Both scan similar report trees; different jobs — **CONSOLIDATE** only in documentation / future shared helper code, not by deleting either.

---

## One-time maintenance & alternate lanes

| Path | Tag | Role |
|------|-----|------|
| `scripts/leads/build_archive_send_batch.py` | ARCHIVE_CANDIDATE | **`contact_master`** / archive send batch lane (not the two daily flows) |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | ARCHIVE_CANDIDATE | Archive commercial precheck |
| `scripts/leads/build_manual_html_outreach_batch.py` | CONSOLIDATE | Manual HTML package builder vs API sender — overlapping “send prep” surface |
| `scripts/leads/mark_outreach_state.py` | KEEP_CORE | Manual single-row **`outreach_contact_state`** edits |
| `scripts/leads/import_operator_outreach_blocklist.py` | KEEP_CORE | Blocklist → suppressions |
| `scripts/leads/add_manual_contact_suppressions.py` | KEEP_CORE | Manual suppression adds |
| `scripts/qa/export_all_known_marketing_contacts.py` | CONSOLIDATE | Known-marketing export; overlaps part of **do-not-repeat master** aggregation |
| `scripts/leads/advanced/prepare_active_workspace.py` | CONSOLIDATE | Name overlap with **`prepare_outbound_campaign_workspace.py`** — avoid mixing without reading both |
| `scripts/leads/advanced/export_marketing_from_contact_master.py` | ARCHIVE_CANDIDATE | Marketing from mart (parallel path) |
| `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` | KEEP_AUDIT | Bounce-driven sync |

Many other `scripts/leads/*.py` (scoring, ChileCompra fetch, dedupe, etc.) are **lead pipeline** or **data ops**, not the two outbound lanes — see [`RUNBOOK.md`](RUNBOOK.md) and [`scripts/README.md`](../scripts/README.md).

---

## Tests (pointer)

Outbound / campaign regression tests live under `tests/` (e.g. `test_run_current_campaign_pipeline.py`, `test_process_broad_marketing_contacts.py`, `test_validate_campaign_csvs.py`, `test_export_gate_audit_csv.py`). **Do not remove** tests when editing docs.

---

## Do not remove (safety-critical)

- **Gate policy:** `candidate_export_gate.py` + `GateContext` inputs — do not change policy lightly.
- **SQLite sidecar:** `outreach_contact_state` — operator memory for “already contacted”.
- **Gmail Sent in SQLite:** `emails` rows for configured Sent folders — blocker truth for exports.
- **Suppressions:** `contact_email_suppression`, `contact_domain_suppression`, and import CLIs.
- **CSV validation:** `validate_campaign_csvs.py`, `csv_contracts.py`.
- **Do-not-repeat master:** `export_do_not_repeat_master.py` — volume lane input to DeepSearch.
- **Post-send marking:** `mark_sent_batch_contacted.py` (and pipeline `post-send` where used).
- **Precision research persistence:** `import_lead_contact_research_csv.py` — only path for **`lead_contact_research`** from reviewed DeepSearch.

---

## Related docs

- [`RUNBOOK.md`](RUNBOOK.md) — full procedures, mailbox ingest, Docker, publish gate
- [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md) — lane semantics
- [`scripts/README.md`](../scripts/README.md) — folder map and QA table
