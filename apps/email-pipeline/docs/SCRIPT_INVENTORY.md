# Script inventory (summary)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-25

**Purpose:** High-level **grouping** of `scripts/` for operators and for **future cleanup planning**. It does **not** list every file. The canonical per-script map is [`SCRIPT_MAP.md`](SCRIPT_MAP.md). Full folder notes: [`../scripts/README.md`](../scripts/README.md). **Tatiana / lab vs daily outbound:** [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md) (Stage 6E1 — not production lanes; future 6E2 may refactor large Tatiana modules).

**Generated output layout:** before deleting or moving anything under [`../reports/out`](../reports/out), run the **planner** [`../scripts/qa/plan_reports_out_cleanup.py`](../scripts/qa/plan_reports_out_cleanup.py) to classify paths and list large files (buckets such as `active_current`, `active_workspace_misc` for other `active/…` paths, `client_pack_latest`, tmp/lab/archive); it does not modify the tree (see [`CRUD_SAFETY.md`](CRUD_SAFETY.md) §7). Optional **move-only** archiver (dry-run default): [`../scripts/tools/archive_reports_out_generated.py`](../scripts/tools/archive_reports_out_generated.py) — same buckets, `--apply` to relocate into `archive/manual_cleanup/…` (no deletes; break-glass). The archiver does not select `client_pack_latest` or `active_workspace_misc` with default include flags; the whole `active/` tree remains protected without `--allow-active-current`.

**Script sprawl (read-only):** before deprecating, re-homing, or deleting a script, run [`../scripts/qa/plan_script_consolidation.py`](../scripts/qa/plan_script_consolidation.py) to see buckets, doc/test references, and wrapper candidates (no file changes; see [`CRUD_SAFETY.md`](CRUD_SAFETY.md) script consolidation policy). Source/refactor **planning** (heuristics, not authority): [`../scripts/qa/plan_source_quality.py`](../scripts/qa/plan_source_quality.py) and [`QUALITY_AND_REFACTOR_STRATEGY.md`](QUALITY_AND_REFACTOR_STRATEGY.md) (prefer `core.*` for new code; no mass import rewrite). The planner labels **compatibility root wrappers** (thin `scripts/<name>.py` → `scripts/leads/advanced/…`) and other buckets; it is **guidance only**—[`SCRIPT_MAP.md`](SCRIPT_MAP.md) stays the operator source of truth. **Shared redaction helpers** (env presence without leaking values) live in [`../src/origenlab_email_pipeline/core/safety.py`](../src/origenlab_email_pipeline/core/safety.py) for scripts and future CRUD checks; **removing or merging scripts** still needs a **later explicit stage** with tests and doc updates. **Entrypoint contracts** are covered by [`../tests/test_operator_entrypoint_contracts.py`](../tests/test_operator_entrypoint_contracts.py) (``--help`` for daily + planner CLIs, safety headers for the break-glass set, and text checks on compatibility wrappers; **removal** of a script path remains a follow-on change, not implied by the test alone).

**Legend**

- **mutates DB:** writes SQLite (or Postgres in migrate tools) in normal use  
- **requires --apply:** destructive/corrective action gated behind `--apply` in typical design  
- **sends email:** can call Gmail to send a message  
- **safe on new machine:** can run on fresh clone with only venv (no private DB) without touching secrets  
- **requires private DB:** needs a real `emails.sqlite` (or path) to be useful  
- **requires Gmail creds:** needs OAuth client/token or Workspace user env for IMAP/API  

Values are **representative**; some scripts in a group may differ. When in doubt, use `--help` and `SCRIPT_MAP.md`.

---

## Daily (outbound + ingest truth)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `qa/export_do_not_repeat_master.py` | R mostly | no | no | no (needs DB) | yes | no |
| `qa/validate_campaign_csvs.py` | no | no | no | **yes** | no | no |
| `leads/process_broad_marketing_contacts.py` | R | no | no | no | yes | no |
| `leads/run_current_campaign_pipeline.py` | if apply | **yes** (import stage) | no | no | yes | no |
| `leads/mark_sent_batch_contacted.py` | **yes** | no | no | no | yes | no |
| `ingest/05_workspace_gmail_imap_to_sqlite.py` | **yes** (ingest) | no | no | no* | optional | **yes** (ingest) |
| `qa/plan_reports_out_cleanup.py` | no | no | no | **yes** | no | no |
| `qa/plan_script_consolidation.py` | no | no | no | **yes** | no | no |
| `qa/plan_source_quality.py` | no | no | no | **yes** | no | no |
| `tools/archive_reports_out_generated.py` | no | **yes** (to move) | no | **yes** | no | no |

*\*Ingest is safe mechanically on a new machine if DB path is writable, but you still need creds to use Gmail. **`plan_reports_out_cleanup` / `plan_script_consolidation`** are read-only planners (the latter scans `scripts/`; optional JSON elsewhere).*

---

## Core (operator tooling, not “daily” for everyone)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `qa/prepare_outbound_campaign_workspace.py` | no (files) | no | no | **yes** | no | no |
| `leads/export_lead_contact_research_queue.py` | R | no | no | no | yes | no |
| `leads/export_next_marketing_recipients.py` | R | no | no | no | yes | no |
| `leads/import_lead_contact_research_csv.py` | **yes** | **yes** | no | no | yes | no |
| `leads/backfill_contacted_from_gmail_sent.py` | if apply | **yes** | no | no | yes | no |

---

## Audit (read-only or “stdout only”)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `qa/export_gate_audit_csv.py` | R | no | no | no | yes | no |
| `qa/check_outbound_readiness.py` | R | no | no | no | no† | no |
| `qa/check_reproducibility.py` | R-RO‡ | no | no | **yes** | no | no |

†useful without DB; weaker readiness. ‡read-only `mode=ro` if DB exists.

---

## Maintenance (mart, leads, commercial, reports)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `mart/build_business_mart.py` | **yes** (rebuild) | N/A | no | no | yes | no |
| `commercial/build_commercial_intel_v1.py` | **yes** | N/A | no | no | yes | no |
| `reports/run_all_reports.py` | R / files | no | no | no | often | no |

---

## Migration (Postgres, optional)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `migrate/sqlite_archive_to_postgres.py` | **PG** | N/A | no | no | source SQLite + **PG URL** | no |
| `qa/validate_sqlite_archive_for_postgres.py` | R | no | no | no | yes (SQLite) | no |

---

## Lab / archive (pilots, Tatiana, archive lane)

Tatiana, `scripts/dataset/`, and `scripts/ml/` are **lab** scope; see [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md). They are **not** interchangeable with daily outbound ops in the tables above.

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `tatiana/run_tatiana_pilot_batch.py` | Varies | maybe | no | Varies | often | if API |
| `leads/build_archive_send_batch.py` | R / files | no | no | no | yes | no |

---

## Break-glass (explicit danger)

| Representative | mutates DB | --apply | sends email | safe new machine | private DB | Gmail creds |
|----------------|------------|---------|------------|------------------|------------|-------------|
| `tools/purge_*.py` | **delete** | **yes** | no | no† | yes | no |
| `qa/send_inline_html_email_via_gmail_api.py` | no | N/A | **yes** | no | no | **yes** |
| `validation/extract_attachment_text.py` | **yes** | N/A | no | no | yes | no |

†running without `--apply` is safer (dry-run), but still needs a path to a DB to mean anything.

---

## Related

- [`SCRIPT_MAP.md`](SCRIPT_MAP.md) — daily commands, break-glass list, `reports/out` policy.  
- [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md) — Tatiana / lab vs production outbound (Stage 6E1).  
- [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) — env and setup.  
- [`CRUD_SAFETY.md`](CRUD_SAFETY.md) — mutation rules.
