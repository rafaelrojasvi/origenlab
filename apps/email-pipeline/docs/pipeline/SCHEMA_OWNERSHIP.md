# SQLite schema ownership

Canonical map of **who defines DDL**, **who ALTERs**, **who rebuilds row data**, and **whether ownership is clean or split**. For ordering when applying multiple layers, see `migrate_sqlite_schema` in [`src/origenlab_email_pipeline/sqlite_migrate.py`](../../src/origenlab_email_pipeline/sqlite_migrate.py).

<a id="m-schema-orchestrated"></a>
## Orchestrated order (optional entrypoint)

`migrate_sqlite_schema(conn)` runs, in order:

1. `init_schema` — archive + mart DDL/migrations + pipeline meta (see [`db.py`](../../src/origenlab_email_pipeline/db.py)).
2. `ensure_leads_tables(..., refresh_view=False)` — leads DDL/migrations (+ optional backfill via `leads_backfill_norms`).
3. `ensure_lead_account_tables(..., refresh_view=False)` — account DDL/migrations.
4. `refresh_lead_match_summary_view` **once** (avoids double view rebuild).

Callers may still use `ensure_leads_tables()` / `ensure_lead_account_tables()` alone; defaults preserve prior behavior (backfill + view refresh).

**Phase 2 adoption:** [`build_business_mart.py`](../../scripts/mart/build_business_mart.py), [`match_leads_to_mart.py`](../../scripts/leads/match_leads_to_mart.py), [`build_lead_account_rollup.py`](../../scripts/build_lead_account_rollup.py), and [`match_lead_accounts_to_existing_orgs.py`](../../scripts/match_lead_accounts_to_existing_orgs.py) call `migrate_sqlite_schema` with the appropriate `SchemaLayer` set. Operational one-shot: [`scripts/pipeline/run_aligned_stack.sh`](../../scripts/pipeline/run_aligned_stack.sh).

---

<a id="m-schema-archive"></a>
## Archive layer

| Object | DDL owner | ALTER / extra DDL | Indexes | Data rebuild | Ownership |
|--------|-----------|-------------------|---------|----------------|-----------|
| `emails` | [`db.py`](../../src/origenlab_email_pipeline/db.py) `SCHEMA_SQL` + `init_schema` | `init_schema` loop (body/attachment columns) | `SCHEMA_SQL` + `idx_emails_body_source_type` in `init_schema` (perf; requires `body_source_type` column) | [`backfill_phase2_2_text_fields.py`](../../scripts/validation/backfill_phase2_2_text_fields.py) | **Clean** |
| `attachments` | `db.py` `SCHEMA_SQL` / `init_schema` | — | `db.py` | ingest | **Clean** |
| `attachment_extracts` | `db.py` `SCHEMA_SQL` / `init_schema` | — | `db.py` | extraction scripts | **Clean** |

---

<a id="m-schema-mart"></a>
## Mart layer (derived, rebuildable)

| Object | DDL owner | ALTER | Indexes | Data rebuild | Ownership |
|--------|-----------|-------|---------|--------------|-----------|
| `contact_master` | [`business_mart_schema.py`](../../src/origenlab_email_pipeline/business_mart_schema.py) | — | same string | [`build_business_mart.py`](../../scripts/mart/build_business_mart.py) DELETE+INSERT | **Clean DDL**; **data** = mart job |
| `organization_master` | `business_mart_schema.py` | — | same | mart job | **Clean** |
| `document_master` | `business_mart_schema.py` (includes preview columns in CREATE) | [`db.py`](../../src/origenlab_email_pipeline/db.py) `init_schema` (`extracted_preview_*`, `preview_quality_score`) | `business_mart_schema.py` | mart job | **Split** (CREATE vs ALTER for same columns on old DBs) |
| `opportunity_signals` | `business_mart_schema.py` | — | same | mart job | **Clean** |

Mart **DDL** is applied inside `init_schema` via `BUSINESS_MART_SCHEMA_SQL`. Mart **rows** are not owned by schema modules.

---

<a id="m-schema-pipeline-meta"></a>
## Pipeline metadata

| Object | DDL owner | ALTER | Indexes | Data | Ownership |
|--------|-----------|-------|---------|------|-----------|
| `pipeline_run` | [`pipeline_meta_schema.py`](../../src/origenlab_email_pipeline/pipeline_meta_schema.py) | — | same | [`pipeline_run_recorder.py`](../../src/origenlab_email_pipeline/pipeline_run_recorder.py) | **Clean** |
| `pipeline_kv` | `pipeline_meta_schema.py` | — | — | `pipeline_run_recorder` | **Clean** |

Also invoked from `init_schema`, `ensure_leads_tables`, `ensure_lead_account_tables`, and recorder helpers.

---

<a id="m-schema-leads"></a>
## Leads layer

| Object | DDL owner | ALTER / deferred indexes | Backfill | View refresh | Ownership |
|--------|-----------|--------------------------|----------|--------------|-----------|
| `external_leads_raw` | [`leads_schema.py`](../../src/origenlab_email_pipeline/leads_schema.py) `LEAD_SCHEMA_SQL` | — | — | — | **Clean** |
| `lead_master` | `leads_schema.py` | `_migrate_lead_master_norm_columns`; legacy buyer/fit/lab columns loop; norm indexes after ALTER | `backfill_lead_master_norm_columns`; `normalize_leads` upserts | via `ensure_leads_tables` / `bi_views` | **Clean module**; **split concerns** (DDL + backfill in same module) |
| `lead_matches_existing_orgs` | `leads_schema.py` | `_migrate_lead_matches_org_columns`; deferred `pipeline_run_id` index | cleared by matching code | — | **Clean** |
| `lead_matches_existing_contacts` | `leads_schema.py` | — (new table) | cleared by matching | — | **Clean** |
| `lead_outreach_enrichment` | `leads_schema.py` | — | import/merge scripts | — | **Clean** |

`ensure_leads_tables_ddl` holds DDL+migrations+indexes without backfill/view; `ensure_leads_tables` wraps optional backfill + view (defaults unchanged).

---

<a id="m-schema-lead-accounts"></a>
## Lead accounts layer

| Object | DDL owner | ALTER / deferred index | Data rebuild | View | Ownership |
|--------|-----------|------------------------|--------------|------|-----------|
| `lead_account_master` | [`lead_accounts_schema.py`](../../src/origenlab_email_pipeline/lead_accounts_schema.py) | — | [`build_lead_account_rollup.py`](../../scripts/build_lead_account_rollup.py) | optional via `refresh_view` | **Clean** |
| `lead_account_aliases` | same | — | rollup | — | **Clean** |
| `lead_account_membership` | same | — | rollup | — | **Clean** |
| `lead_account_matches_existing_orgs` | same | `ADD pipeline_run_id` + index after (legacy DBs) | [`match_lead_accounts_to_existing_orgs.py`](../../scripts/match_lead_accounts_to_existing_orgs.py) | — | **Clean** (deferred index pattern) |
| `lead_account_overrides` | same | — | manual | — | **Clean** |

---

<a id="m-schema-views"></a>
## Views

| Object | Owner | Behavior |
|--------|-------|------------|
| `v_lead_match_summary` | [`bi_views.py`](../../src/origenlab_email_pipeline/bi_views.py) `refresh_lead_match_summary_view` | Prerequisites checked before DROP; transactional replace; returns status string. Core vs full SQL depends on account tables. |

---

<a id="m-schema-summary"></a>
## Clean vs split (summary)

- **Split:** `document_master` (CREATE in mart schema + ALTER in `db.py` for preview columns on old DBs).
- **Otherwise:** ownership aligns with one primary module per layer; operational DELETE/INSERT lives in named scripts, not schema modules.
