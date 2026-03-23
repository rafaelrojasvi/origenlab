# Email Pipeline Architecture

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-24

<a id="m-eparch-flow"></a>
## Data flow

1. PST → mbox ([`scripts/ingest/01_convert_pst.sh`](../scripts/ingest/01_convert_pst.sh))
2. mbox → SQLite ([`scripts/ingest/02_mbox_to_sqlite.py`](../scripts/ingest/02_mbox_to_sqlite.py))
3. SQLite → JSONL ([`scripts/ingest/03_sqlite_to_jsonl.py`](../scripts/ingest/03_sqlite_to_jsonl.py))
4. Derived layers: business mart, lead pipeline, reports, optional ML exploration

<a id="m-eparch-docs"></a>
## Canonical architecture docs

- Business mart: [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md)
- Business signal filters: [`pipeline/BUSINESS_FILTERING.md`](pipeline/BUSINESS_FILTERING.md)
- Lead flow: [`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md)
- Schema ownership: [`pipeline/SCHEMA_OWNERSHIP.md`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-orchestrated)
- Phase-2 extraction chain: [`pipeline/PHASE2_EMAIL_PIPELINE.md`](pipeline/PHASE2_EMAIL_PIPELINE.md)

<a id="m-eparch-qa-trust"></a>
## Operational trust (QA) layer

Sits **above** the SQLite database and **repo-local operational outputs**, not inside the ingest pipeline:

- **Inputs:** [`lead_master`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-leads) (via SQLite), [`reports/out/client_pack_latest/summary.json`](../reports/out/README.md) (snapshot from [`build_leads_client_pack.py`](../scripts/reports/build_leads_client_pack.py)), hunt + readiness + top20 CSVs under [`reports/out/active/`](../reports/out/README.md), optional [`docs/generated/CONTACT_READINESS_AUDIT.md`](generated/CONTACT_READINESS_AUDIT.md) for DB path provenance, URL columns in hunt/top20 for link checks.
- **Logic:** [`operational_trust.py`](../src/origenlab_email_pipeline/operational_trust.py) implements shared checks; [`scripts/qa/`](../scripts/qa/) CLIs invoke it and set exit codes from **critical** failures only.
- **Outputs:** Scorecards [`reports/out/active/operational_trust_scorecard.json`](../reports/out/README.md) and [`docs/generated/operational_trust_scorecard.md`](generated/operational_trust_scorecard.md) (from [`audit_operational_trust.py`](../scripts/qa/audit_operational_trust.py)).
- **Publication:** The gate is a **pre-share consistency** step; it does not replace human review of client-facing narrative. Procedure: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa).

<a id="m-eparch-constraints"></a>
## Design constraints

- Prefer reproducible scripts and deterministic outputs.
- Keep extraction/reporting logic separate from historical narrative docs.
- Use runbooks for execution; use this doc for architecture orientation. See [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path).
