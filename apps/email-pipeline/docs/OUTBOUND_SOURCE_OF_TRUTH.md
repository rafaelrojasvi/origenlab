# Outbound Source Of Truth

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-15

Single reference for how outbound decisions should use SQLite layers, operator state, and gate policy.

## Canonical operator CLIs (do not bypass)

From `apps/email-pipeline/`:

| Lane | Primary command | Purpose |
|------|-----------------|--------|
| **Archive (warm revival)** | `uv run python scripts/leads/build_archive_send_batch.py` | Full batch: audit → shortlist → gate snapshot → commercial precheck → `archive_outreach_send_ready.csv` / `archive_outreach_review_required.csv`. Default ``company_intro`` ordering favors non–free-personal domains, org procurement signals, and (when ``emails`` has ``sender``/``recipients``) historical **LabDelivery / voice-domain** touches (`last_contacted_by_labdelivery`, `labdelivery_last_contact_at`); tune pool size with ``--shortlist-limit`` / ``--audit-limit``. |
| **Archive audit only** | Same script with `--audit-only` | Writes `archive_outreach_audit.csv` + `archive_outreach_audit_summary.json` only (no shortlist/precheck). Prefer this over legacy standalone audit scripts. |
| **Lead (curated prospects)** | `uv run python scripts/leads/export_next_marketing_recipients.py` | Next N from `lead_master` using the **same** shared export gate as Streamlit’s queue. |

**Not a send lane:** ChileCompra / `external_leads_raw` / `lead_master` **ingest and scoring** are prospecting data prep, not a parallel mailbox-send path. Outbound still flows through one of the two lanes above plus human review.

**Advanced / exploratory (not default daily workflow):**

- `scripts/leads/advanced/export_archive_outreach_candidates.py` — thin **audit-only** wrapper; prefer `build_archive_send_batch.py --audit-only`.
- `scripts/leads/advanced/export_marketing_from_contact_master.py` — optional `contact_master` pool export; **`contact_master` is not CRM truth**; use for exploration, not as the default archive batch.

**Streamlit** (`apps/business_mart_app.py`): **review, read/write sidecars** (suppression, outreach state, visibility), and surfaces that call the **same library functions** as the CLIs. It must **not** be treated as the sole source of “what we exported for this send” — the canonical commands above produce reproducible artifacts under `reports/out/...`.

### Shared runtime defaults (`outbound_core`)

[`outbound_core.py`](../src/origenlab_email_pipeline/outbound_core.py) centralizes **how** operators resolve mailbox identity, default Sent folders, and **which** `GateContext` constructor applies per lane (`gate_context_for_archive_batch` uses stricter contact-graph noise; `gate_context_for_lead_master_export` matches `lead_master` / Cola). Policy remains in [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py) and [`marketing_export_context.py`](../src/origenlab_email_pipeline/marketing_export_context.py). Summary JSON from archive runs includes a nested **`outbound_run`** block (schema version, lane, paths, counts) for drift-resistant auditing; the lead CLI can emit a sibling summary with `--write-outbound-summary`.

**Blocker-memory regression tests:** integration tests exercise the canonical **lead** queue (`tests/test_next_marketing_queue_outbound_integration.py`) and **archive** batch builder (`tests/test_archive_lane_outbound_integration.py`) against real SQLite fixtures — Sent-history norms (default Sent folders only), `outreach_contact_state`, and suppression — without changing gate policy.

**Operator trust:** short runnable checklist (preflight, which CSV/JSON to trust, after-send memory) — [`pipeline/OUTBOUND_OPERATOR_CHECKLIST.md`](pipeline/OUTBOUND_OPERATOR_CHECKLIST.md). To pretty-print **`outbound_run`** from a saved summary: [`print_outbound_run_summary.py`](../scripts/qa/print_outbound_run_summary.py).

## Executive model

Current outbound is a **two-lane model** with one shared blocker policy:

1. **Archive-first outreach lane (primary warm revival):** revive warm historical contacts from archive-derived tables.
2. **Lead-based outreach lane (curated prospecting):** contact selected external leads from `lead_master`.

Both lanes must use the same eligibility policy in [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py).

## Layer model (purpose, truth type, writers/readers)

| Layer | Main objects | Purpose | Truth type | Main writers | Main readers |
|------|------|------|------|------|------|
| Raw archive | `emails`, `attachments`, `attachment_extracts` | Preserve historical mailbox evidence | **Truth (evidence)** | ingest + extraction scripts | mart builders, reporting, intel |
| Rebuildable mart | `contact_master`, `organization_master`, `document_master`, `opportunity_signals` | Deterministic projections from archive for analysis/queueing | **Heuristic / derived** | `build_business_mart.py` | outreach queues, lead matching, reports |
| Leads | `external_leads_raw`, `lead_master`, lead match/reconcile tables | Curated external prospect pipeline | **Operational truth for prospecting** | leads ingest/normalize/score/match/reconcile | Streamlit queue, exports, QA |
| Commercial intel | `commercial_*` facts + candidate/review tables | Signal rollups + durable review workflow | **Mixed: heuristic + workflow state** | commercial build/review scripts | operator review queues/reports |
| Operator sidecars | `contact_email_suppression`, `outreach_contact_state` | Durable outbound memory and hard blockers | **Workflow/safety state** | operator scripts + app actions | shared export gate and audits |
| Policy in code | `candidate_export_gate.py` (not a table) | Enforce consistent blockers across lanes | **Policy logic** | maintained in code | both outbound lanes |

See also DDL ownership details in [`pipeline/SCHEMA_OWNERSHIP.md`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-orchestrated).

## Source-of-truth guidance

### When to use `lead_master`

Use `lead_master` for **curated prospecting operations**:

- external/public-source leads that are normalized and scored
- weekly focus and operator outbound shortlist work
- workflows where `source_name` and `source_record_id` lineage matters

### When to use `contact_master`

Use `contact_master` for **historical archive revival** and exploration:

- finding warm contacts/institutions from historical email evidence
- ranking/revival heuristics over prior relationship graph
- archive-first queue construction before shared gate filtering

`contact_master` is **not CRM truth**. It is a mart projection from historical mail traffic and can include noisy or non-buyer addresses.

### Why `contacto@origenlab.cl` matters

`contacto@origenlab.cl` is the **current sending and blocker mailbox context** for outbound controls:

- Sent-history blocking (already-contacted detection via Sent folders)
- operator outreach memory (`outreach_contact_state`)
- suppression/operational safety workflow

It is **not** the source of the historical network itself. Historical relationship evidence still comes from the archive + mart layers.

## Outbound workflow guidance

Recommended operating order:

1. Start with **archive-first lane** for warm revival opportunities.
2. Add **lead-based lane** as a curated secondary channel.
3. Apply the same shared gate for both lanes.
4. Keep outbound human-reviewed and batch-controlled.

### Shared gate responsibilities

[`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py) centralizes blockers, including:

- invalid/internal addresses
- suppression list membership
- Sent-history conflicts (for current sender context)
- `outreach_contact_state` blocking states (`contacted`, `replied`, `snoozed`)
- supplier/noise heuristics

### Sent history vs outreach state

- **Sent history:** inferred technical fact from mailbox activity (someone was already sent from current sender context).
- **`outreach_contact_state`:** explicit operator-managed lifecycle state and memory per contact.

### Suppression vs outreach state

- **Suppression (`contact_email_suppression`):** hard safety block (do not contact).
- **Outreach state (`outreach_contact_state`):** lifecycle memory that may block based on state policy.

## Streamlit/operator guidance (how tabs map to lanes)

- **Qué hacer hoy:** operator command center; daily priorities and handoffs.
- **Casos para revisar:** review-focused queueing and manual decision support (quality/safety check surface).
- **Cola outreach marketing:** lead-based lane operational queue from `lead_master` through shared gate (same policy as `export_next_marketing_recipients.py`).
- **Borrador comercial:** drafting support surface; assists composition, does not replace gate/human review.

Operator rule of thumb:

- Use archive-first candidates for warm revival and history-aware opportunities.
- Use `lead_master` queue for curated net-new prospecting.
- Never bypass shared gate + human review before sending.
- **Canonical CLIs** (`build_archive_send_batch.py`, `export_next_marketing_recipients.py`) produce the **record of what was run** for a batch; **Streamlit** is for ongoing **review and read/write sidecars**, not a substitute for those artifacts.
- When mailbox or DB freshness is uncertain, run **`check_outbound_readiness.py`** before generating a batch.
- **After sending**, refresh **Sent** ingest for `contacto@origenlab.cl` and update **`outreach_contact_state`** / **suppression** so the next export does not re-surface the same contacts.

## Commercial precheck vs shared export gate (archive batch)

The **shared export gate** ([`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py)) is the **primary hard blocker** for invalid/internal mail, suppression, Sent history, blocking outreach states, supplier/noise, etc.

**Commercial intel precheck** (archive batch step that reads `contact_candidate` / org / opportunity rows) adds **Engine B** context. Policy (archive batch builder):

- **Default (`commercial_precheck_policy=advisory`):** if precheck would recommend **drop** only because of commercial status (suppressed/rejected), the row is placed in **`review_required`** with `final_decision_path=advisory_commercial_drop`, not silently omitted.
- **Strict (`--strict-commercial-drop`):** those rows are **final drops** (omitted from both `send_ready` and `review_required` CSVs), matching the earlier “precheck drop” behavior.

Gate-ineligible rows are always final drops regardless of this flag. See `archive_outreach_build_summary.json` for `commercial_precheck_policy` and `strict_commercial_drop`.

## Archive outreach status

Archive outreach is now a **parallel, operator-usable path** built from archive-derived contacts and filtered by the same current gate policy.

- It should be treated as **production-usable with operator review**.
- It is not a replacement for curated lead operations.
- Keep it as a complementary lane with explicit human decision checkpoints.

## See also

- Operator checklist (artifacts, review order, after-send memory): [`pipeline/OUTBOUND_OPERATOR_CHECKLIST.md`](pipeline/OUTBOUND_OPERATOR_CHECKLIST.md)

