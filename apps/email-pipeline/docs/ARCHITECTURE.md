# Email Pipeline Architecture

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-13

<a id="m-eparch-flow"></a>
## Data flow

1. PST → mbox ([`scripts/ingest/01_convert_pst.sh`](../scripts/ingest/01_convert_pst.sh))
2. mbox → SQLite ([`scripts/ingest/02_mbox_to_sqlite.py`](../scripts/ingest/02_mbox_to_sqlite.py))
3. SQLite → JSONL ([`scripts/ingest/03_sqlite_to_jsonl.py`](../scripts/ingest/03_sqlite_to_jsonl.py))
4. Derived layers: business mart, lead pipeline, reports, optional ML exploration
5. Commercial intelligence v1 (signals + durable candidate review state)

<a id="m-eparch-docs"></a>
## Canonical architecture docs

- Business mart: [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md)
- Commercial intelligence v1: [`pipeline/COMMERCIAL_INTEL_V1.md`](pipeline/COMMERCIAL_INTEL_V1.md)
- Business signal filters: [`pipeline/BUSINESS_FILTERING.md`](pipeline/BUSINESS_FILTERING.md)
- Lead flow: [`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md)
- Outbound source-of-truth model (two-lane + shared gate): [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md)
- Schema ownership: [`pipeline/SCHEMA_OWNERSHIP.md`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-orchestrated)
- Phase-2 extraction chain: [`pipeline/PHASE2_EMAIL_PIPELINE.md`](pipeline/PHASE2_EMAIL_PIPELINE.md)

<a id="m-eparch-qa-trust"></a>
## Operational trust (QA) layer

Sits **above** the SQLite database and **repo-local operational outputs**, not inside the ingest pipeline:

- **Inputs:** [`lead_master`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-leads) (via SQLite), [`reports/out/client_pack_latest/summary.json`](../reports/out/README.md) (snapshot from [`build_leads_client_pack.py`](../scripts/reports/build_leads_client_pack.py)), hunt + readiness + top20 CSVs under [`reports/out/active/`](../reports/out/README.md), optional [`docs/generated/CONTACT_READINESS_AUDIT.md`](generated/CONTACT_READINESS_AUDIT.md) for DB path provenance, URL columns in hunt/top20 for link checks.
- **Logic:** [`operational_trust.py`](../src/origenlab_email_pipeline/operational_trust.py) is a thin facade that re-exports checks from focused modules (`operational_trust_pack`, `operational_trust_cohort`, `operational_trust_evidence`, `operational_trust_provenance`, `operational_trust_csv`, `operational_trust_paths`, `operational_trust_types`). [`scripts/qa/`](../scripts/qa/) CLIs import the facade and set exit codes from **critical** failures only.
- **Outputs:** Scorecards [`reports/out/active/operational_trust_scorecard.json`](../reports/out/README.md) and [`docs/generated/operational_trust_scorecard.md`](generated/operational_trust_scorecard.md) (from [`audit_operational_trust.py`](../scripts/qa/audit_operational_trust.py)).
- **Publication:** The gate is a **pre-share consistency** step; it does not replace human review of client-facing narrative. Procedure: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa).

<a id="m-eparch-export-gate"></a>
## Cold outreach export eligibility (shared gate)

Separate from the **publication** QA gate: **marketing / cold-outreach candidate** selection uses [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py). **`evaluate_export_eligibility()`** is invoked from:

- [`next_marketing_queue.py`](../src/origenlab_email_pipeline/next_marketing_queue.py) → `compute_next_marketing_recipients()` (Streamlit **Cola outreach marketing** reads `lead_master` through this path).
- [`export_marketing_from_contact_master.py`](../scripts/leads/export_marketing_from_contact_master.py) (optional pool from **`contact_master`**).

So the **lead** and **`contact_master`** export paths share one policy module (`evaluate_export_eligibility`). Block reasons include invalid email, internal domains, suppression list, addresses already in **Sent**, **`outreach_contact_state`** in **`contacted`** / **`replied`** / **`snoozed`**, configured **supplier** domains, and **noise** heuristics on email or institution name. **`contact_master`** uses a **stricter** subset of email-noise rules (mail-graph senders) than **`lead_master`**; audit CSVs apply the same strictness per row source. Current sender/blocker context is the OrigenLab mailbox (`contacto@origenlab.cl`) for Sent-history and operator memory.

**Truth boundary:** This gate removes known **explicit leaks**; it does not make **`contact_master`** CRM-grade buyer truth or justify high-volume autonomous outbound. **`lead_master`** remains the cleaner external-prospect source; archive and mart tables remain **evidence** and **exploration** layers. Use the canonical lane guidance in [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md). Read-only auditing: [`scripts/qa/export_candidate_audit.py`](../scripts/qa/export_candidate_audit.py). Procedure and tests: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-cold-export-gate).

<a id="m-eparch-constraints"></a>
## Design constraints

- Prefer reproducible scripts and deterministic outputs.
- Keep extraction/reporting logic separate from historical narrative docs.
- Use runbooks for execution; use this doc for architecture orientation. See [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path).
