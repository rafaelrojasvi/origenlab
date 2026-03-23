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

<a id="m-eparch-constraints"></a>
## Design constraints

- Prefer reproducible scripts and deterministic outputs.
- Keep extraction/reporting logic separate from historical narrative docs.
- Use runbooks for execution; use this doc for architecture orientation. See [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path).
