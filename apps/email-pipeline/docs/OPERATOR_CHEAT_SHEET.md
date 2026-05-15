# Operator cheat sheet — which script should I run?

**Status:** canonical (operator aid)  
**Owner:** email-pipeline-maintainers  
**Last reviewed:** 2026-05-14

Short answers for day-to-day work. **Canonical procedures and tables:** [`SCRIPT_MAP.md`](SCRIPT_MAP.md) · [`RUNBOOK.md`](RUNBOOK.md). This page is **not** a substitute for those runbooks.

---

## 1. Normal outbound safety refresh

| | |
|--|--|
| **Run** | `uv run python scripts/qa/refresh_outbound_safety_memory.py` (or the same steps manually — see [`RUNBOOK.md`](RUNBOOK.md) daily outbound / anti-repeat sequence) |
| **Produces** | Refreshed CSVs under `reports/out/active/` (e.g. contacted-all, all-known marketing, DNR master, hygiene/readiness checks per [`SCRIPT_MAP.md`](SCRIPT_MAP.md)) |
| **When** | Before a new send cycle, after major mailbox changes, or when anti-repeat artifacts may be stale |

---

## 2. Broad / volume marketing lane

| Step | Script | Output / role |
|------|--------|----------------|
| DNR input | `scripts/qa/export_do_not_repeat_master.py` | `active/current/do_not_repeat_master.*` |
| Validate reviewed CSV | `scripts/qa/validate_campaign_csvs.py` … `--kind marketing_contacts` | Exit code / JSON |
| Gate + split | `scripts/leads/process_broad_marketing_contacts.py` | `send_ready_marketing.csv`, splits, summary JSON |

**Do not skip:** `validate_campaign_csvs.py` (strict), gate-backed processor, and **Sent history** in SQLite (ingest) before trusting exports — see [`RUNBOOK.md`](RUNBOOK.md) and [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md).

---

## 3. Precision lead / research lane

| Step | Script | Output / role |
|------|--------|----------------|
| Prepare workspace | `scripts/qa/prepare_outbound_campaign_workspace.py` | `active/current/` campaign layout |
| Queue export | `scripts/leads/export_lead_contact_research_queue.py` | **Requires `--out`:** you choose the CSV path. `research_queue.csv` (often under `active/current/`) is a **convention / example** from [`SCRIPT_MAP.md`](SCRIPT_MAP.md), not a default filename. |
| Import reviewed rows | `scripts/leads/import_lead_contact_research_csv.py` | **`--apply`** required to write DB |
| Orchestrator | `scripts/leads/run_current_campaign_pipeline.py` | `prepare` / `process-reviewed` / `post-send` stages |

**Human review:** reviewed DeepSearch CSV, `send_ready.csv`, and any draft content — nothing auto-sends.

---

## 4. After sending emails

1. **Gmail Sent → SQLite:** `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` (correct Sent folder label — [`RUNBOOK.md`](RUNBOOK.md)). **`--help` is safe**; a **normal ingest** run **writes to SQLite** and **contacts Gmail/IMAP**. **`--list-folders`** (see `--help`) lists mailbox labels and **exits before** opening SQLite for ingest — that path is **not** a substitute for understanding that default ingest mutates the DB.
2. **Mark batch contacted:** `scripts/leads/mark_sent_batch_contacted.py` (`--batch-file`, `--source`, `--updated-by`).
3. **Refresh safety memory again** (§1) so the next export sees Sent + state truth.

---

## 5. Research automation

| Mode | Script | Note |
|------|--------|------|
| Heavy / light | `scripts/research/run_deep_research_prospecting.py` | `--research-mode heavy` = true Deep Research models only; light = cheaper daily rotation (see [`SCRIPT_MAP.md`](SCRIPT_MAP.md) and [`DEEP_RESEARCH_AUTOMATION_PLAN.md`](DEEP_RESEARCH_AUTOMATION_PLAN.md)) |

**Does not send:** stops before live send; you review artifacts under `active/current/research_automation/…`.

---

## 6. Archive / revival lane

| Script | Use |
|--------|-----|
| `scripts/leads/build_archive_send_batch.py` | **`contact_master`** / archive-derived batch: audit, shortlist, precheck, `send_ready` / review paths |

**Different from** `scripts/leads/export_next_marketing_recipients.py`, which exports **`lead_master`** through the shared gate for the **lead** lane. That CLI **requires `--out` / `-o`**; **`send_ready.csv`** is a **recommended filename / convention**, not an automatic default (same shared gate family, different lane — [`SCRIPT_MAP.md`](SCRIPT_MAP.md) archive vs daily table).

---

## 7. Maintenance / audit only (read-only or planning)

| Script | Role |
|--------|------|
| `scripts/qa/check_outbound_readiness.py` | Readiness / config checks |
| `scripts/qa/validate_contacted_csv_coverage.py` | Strict CSV coverage vs gate inputs (often in refresh chain) |
| `scripts/qa/plan_script_consolidation.py` | **Planning:** classifies `scripts/` — no file changes |
| `scripts/qa/plan_reports_out_cleanup.py` | **Planning:** `reports/out` buckets — no file changes |

---

## 8. Do not run casually

- **Postgres migrate:** `scripts/migrate/sqlite_*_to_postgres.py` — **optional**; scratch DB first; see [`RUNBOOK.md`](RUNBOOK.md#m-eprun-postgres-optional).
- **Send mail:** `scripts/qa/send_inline_html_email_via_gmail_api.py` — break-glass; can send real mail.
- **Purge / mart rebuild / commercial rebuild / extract rebuild** — break-glass; read `--help` and [`SCRIPT_MAP.md`](SCRIPT_MAP.md#break-glass-scripts).
- **Bounce sync writes:** `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` — review evidence; **`--apply`** mutates state.

---

## 9. If confused

1. Open **[`SCRIPT_MAP.md`](SCRIPT_MAP.md)** (operator index) then **[`RUNBOOK.md`](RUNBOOK.md)** (step-by-step).
2. Do **not** guess between two similarly named scripts — e.g. workspace prep: [`SCRIPT_INVENTORY.md`](SCRIPT_INVENTORY.md#workspace-prep-which-script) (stable anchor).
3. Do **not** bypass **DNR**, **export gate**, or **Sent-history** checks — they are intentional fail-closed safety.

**Postgres / API:** optional or absent for daily ops; see [`audits/POSTGRES_API_PIPELINE_MESS_AUDIT.md`](audits/POSTGRES_API_PIPELINE_MESS_AUDIT.md) if you need context.
