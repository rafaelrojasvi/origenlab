# Outbound Source Of Truth

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-13

Single reference for how outbound decisions should use SQLite layers, operator state, and gate policy.

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
- **Cola outreach marketing:** lead-based lane operational queue from `lead_master` through shared gate.
- **Borrador comercial:** drafting support surface; assists composition, does not replace gate/human review.

Operator rule of thumb:

- Use archive-first candidates for warm revival and history-aware opportunities.
- Use `lead_master` queue for curated net-new prospecting.
- Never bypass shared gate + human review before sending.

## Archive outreach status

Archive outreach is now a **parallel, operator-usable path** built from archive-derived contacts and filtered by the same current gate policy.

- It should be treated as **production-usable with operator review**.
- It is not a replacement for curated lead operations.
- Keep it as a complementary lane with explicit human decision checkpoints.

