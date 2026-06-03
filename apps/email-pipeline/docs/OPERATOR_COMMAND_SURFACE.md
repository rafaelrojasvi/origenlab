# Operator command surface

Status: canonical (navigation)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-02 (Phase 6A)

**Start here** for *what to run*. Full tags, removed paths, and safety prose: [`SCRIPT_MAP.md`](SCRIPT_MAP.md). Procedures: [`RUNBOOK.md`](RUNBOOK.md). Post-send order: [`pipeline/POST_SEND_SAFE_LOOP.md`](pipeline/POST_SEND_SAFE_LOOP.md).

**Working directory:** `cd apps/email-pipeline` · **Truth today:** SQLite + Gmail Sent in `emails` · **Not send approval:** Postgres mirror / dashboard LISTO.

**Mutates?** — **No** = read-only or reports only; **Reports** = writes under `reports/out/` only; **SQLite** = may write DB (often dry-run default); **Yes** = mutates without dry-run default on common paths.

---

## 1. Daily commands (OPS_DAILY / lane core)

Two lanes: **volume marketing** (`reviewed_marketing_contacts.csv` → `send_ready_marketing.csv`) and **precision leads** (`reviewed_deepsearch.csv` → `send_ready.csv`). Workspace: `reports/out/active/current/`.

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/qa/prepare_outbound_campaign_workspace.py` | Init/archive `active/current/` + manifest | Reports | Before a new outbound round |
| `scripts/qa/export_do_not_repeat_master.py` | DNR lists for DeepSearch + volume processor | Reports | Start of volume lane / weekly refresh |
| `scripts/research/run_deep_research_prospecting.py` | Automated research → review-ready batch (no send) | Reports | Weekly/heavy or light daily research |
| `scripts/qa/validate_campaign_csvs.py` | CSV contract checks | No | Before process/import; after DeepSearch export |
| `scripts/leads/process_broad_marketing_contacts.py` | Gate volume contacts → send-ready marketing | Reports | After `reviewed_marketing_contacts.csv` |
| `scripts/leads/export_next_marketing_recipients.py` | `send_ready.csv` from `lead_master` + gate | Reports | Precision-style list from lead master |
| `scripts/leads/run_current_campaign_pipeline.py` | Precision lane: prepare / process-reviewed / post-send | Reports; SQLite with `--apply` on process-reviewed | Named precision campaign slug |
| `scripts/leads/export_lead_contact_research_queue.py` | `research_queue.csv` for DeepSearch | Reports | Precision prepare stage |
| `scripts/leads/import_lead_contact_research_csv.py` | Load reviewed DeepSearch → `lead_contact_research` | SQLite (`--apply`) | After `reviewed_deepsearch.csv`; dry-run first |
| `scripts/leads/mark_sent_batch_contacted.py` | Post-send `outreach_contact_state` | SQLite | After human send; real batch metadata |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Gmail → `emails` (Sent/inbox) | SQLite | Same day/week as send; post-send ingest |
| `scripts/qa/export_outreach_contacted_all.py` | Auxiliary contacted-all CSV | Reports | Safety chain / anti-repeat inputs |
| `scripts/qa/refresh_outbound_safety_memory.py` | DNR + contacted-all + strict validation chain | Reports; reads SQLite | Daily or before send; stops on hard failure |

---

## 2. Safety / audit commands (OPS_AUDIT / OPS_CORE)

Trust checks and hygiene — **not** the send list builders. Prefer **`operator_status.py`** before ambiguous sends.

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/qa/operator_status.py` | READY / CAUTION / BLOCKED snapshot | No | Quick health before outbound work |
| `scripts/qa/check_outbound_readiness.py` | Config / readiness checks | No | Pre-flight debugging |
| `scripts/qa/run_daily_health_report.py` | Combined health (NDR dry-run, drift, mirror hints) | Reports | Daily ops review |
| `scripts/qa/validate_contacted_csv_coverage.py` | Strict contacted CSV vs Sent/gate | No | Part of `refresh_outbound_safety_memory` |
| `scripts/qa/export_contacted_lead_overlap_audit.py` | Overlap vs Sent, state, suppressions | Reports | Pre-import / pre-send |
| `scripts/qa/export_gate_audit_csv.py` | Per-row gate flags | Reports | Explain why rows blocked |
| `scripts/qa/export_outreach_volume_rollup.py` | Saturation metrics by source | Reports | Capacity planning (not DNR export) |
| `scripts/qa/check_reports_out_active_hygiene.py` | Unexpected files under `active/` | No | After manual exports / cleanup |
| `scripts/qa/build_ndr_review_queue.py` | NDR review batches + suggested allowlists | Reports | Before targeted NDR `--apply` |
| `scripts/leads/import_operator_outreach_blocklist.py` | Blocklist → suppressions | SQLite | Policy blocklist import |
| `scripts/leads/add_manual_contact_suppressions.py` | Manual suppression adds | SQLite | Operator-confirmed blocks |
| `scripts/qa/plan_reports_out_cleanup.py` | Classify `reports/out` (plan only) | No | Before archiving generated files |
| `scripts/qa/plan_script_consolidation.py` | Classify `scripts/` buckets (plan only) | No | Refactor / deprecation planning |

---

## 3. Post-send commands

Run after Sent mail, NDRs, or suppression changes. Order: [`POST_SEND_SAFE_LOOP.md`](pipeline/POST_SEND_SAFE_LOOP.md).

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Ingest Sent (no `--replace-source`) | SQLite | Refresh Gmail evidence |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | NDR / optional human-reported scan; suppression apply | SQLite (`--apply`) | After bounces; prefer `--emails-file` + `--only-code` |
| `scripts/leads/audit_contacted_universe.py` | Rebuild exclusion CSVs from SQLite | Reports | Before digest |
| `scripts/qa/refresh_outbound_safety_memory.py` | Safety export chain | Reports | Post-send refresh |
| `scripts/qa/build_post_send_digest.py` | Post-send digest CSV/MD/JSON | Reports | After `audit_contacted_universe` |
| `scripts/qa/audit_prospectos_safety_drift.py` | Prospect vs safety sidecars | Reports | Drift check (≠ send failure) |
| `scripts/qa/audit_institution_grouping.py` | Institution grouping audit | Reports | Strategy only |
| `scripts/ops/refresh_render_dashboard_once.sh` | Postgres mirror refresh (optional) | Postgres mirror | Reporting only; not send truth |

---

## 4. Campaign-wave commands (OPS_MAINT)

Named waves only — **not** daily volume/precision lanes. See [`CAMPAIGN_ONEOFF_RETIREMENT_AUDIT`](audits/CAMPAIGN_ONEOFF_RETIREMENT_AUDIT_20260602.md).

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/qa/build_presentacion_origenlab_review.py` | Presentation review queue | Reports | Presentation campaign triage |
| `scripts/qa/build_presentacion_origenlab_quality.py` | Presentation quality pass | Reports | After review CSVs |
| `scripts/qa/build_presentacion_batch1_presend_audit.py` | Batch 1 pre-send audit | Reports | Before presentation send |
| `scripts/qa/build_presentacion_prospectos_merge.py` | Prospectos + lead-research merge | Reports | Presentation overlay |
| `scripts/qa/build_cyber_outreach_campaign.py` | Cyber-day package + gate audit | Reports | Cyber campaign wave |
| `scripts/qa/build_cyber_campaign_context_audit.py` | Cyber context / evidence audit | Reports | Cyber evidence review |

---

## 5. Postgres / experimental (parked)

**Optional.** Read [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md) before migrate/sync. Scratch Postgres first; explicit approval for `--replace` loaders.

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/qa/verify_dashboard_postgres_mirror.py` | Dashboard mart mirror parity | No | After mirror load |
| `scripts/qa/verify_outbound_sidecar_postgres_mirror.py` | Outbound sidecar parity | No | After mirror load |
| `scripts/qa/verify_lead_research_postgres_mirror.py` | Lead research mirror parity | No | After mirror load |
| `scripts/qa/verify_catalog_postgres_mirror.py` | Catalog mirror parity | No | After mirror load |
| `scripts/qa/verify_commercial_deals_postgres_mirror.py` | Commercial deals parity | No | After mirror load |
| `scripts/qa/validate_sqlite_archive_for_postgres.py` | Pre-migrate SQLite checks | No | Before migrate |
| `scripts/sync/sync_lead_research_postgres_mirror.py` | SQLite → Postgres lead_intel | Postgres (opt-in) | Approved mirror promotion |
| `scripts/sync/load_equipment_opportunity_mirror.py` | Equipment queue CSV → Postgres | Postgres (dry-run default) | Approved commercial mirror |
| `scripts/ops/cloud_postgres_url.py` | Validate/redact Postgres URL | No | Shell / ops prep |
| `scripts/migrate/sqlite_*_to_postgres.py` | Bulk SQLite → Postgres load | Postgres (**TRUNCATE**) | **Parked** — approved migration only |
| `scripts/sync/sync_dashboard_postgres_mirror.py` | Dashboard mirror load | Postgres | **Parked** — dashboard stack only |

---

## 6. Break-glass commands

High blast radius: send, purge, rebuild, broad `--apply`, or `--replace-source`. Read `--help` and file `SAFETY` headers. Confirm `ORIGENLAB_SQLITE_PATH`.

| Path | Purpose | Mutates? | When to use |
|------|---------|----------|-------------|
| `scripts/qa/send_inline_html_email_via_gmail_api.py` | Send HTML via Gmail API | **Sends mail** | Intentional API send only |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | Broad NDR `--apply` (no allowlist) | SQLite | Avoid — use targeted apply |
| `scripts/tools/purge_contact_emails_from_sqlite.py` | Multi-table email purge | SQLite (`--apply`) | GDPR / correction — dry-run first |
| `scripts/tools/purge_email_domain_from_sqlite.py` | Domain purge | SQLite (`--apply`) | Same |
| `scripts/tools/purge_mailbox_from_sqlite.py` | Mailbox purge | SQLite (`--apply`) | Same |
| `scripts/mart/build_business_mart.py` | Rebuild business mart | SQLite DELETE/rebuild | Scheduled mart rebuild |
| `scripts/commercial/build_commercial_intel_v1.py` | Rebuild commercial facts | SQLite | Commercial rebuild |
| `scripts/leads/advanced/build_lead_account_rollup.py` | Rebuild `lead_account_*` | SQLite DELETE/rebuild | Lead-account maintenance |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | Dedupe canonical Gmail rows | SQLite (`--apply`) | Duplicate repair |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | `--replace-source` folder refresh | SQLite DELETE+insert | Repair bad ingest — not safe loop |
| `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` | Bounce-driven state sync | SQLite (`--apply`) | Evidence-reviewed bounce batch |
| `scripts/tools/archive_reports_out_generated.py` | Move `reports/out` artifacts | Files (`--apply`) | Cleanup after plan |
| `scripts/validation/extract_attachment_text.py` | Attachment text extract/rebuild | SQLite (rebuild paths) | Attachment pipeline maintenance |

---

## 7. Lab / archive commands

**Not daily outbound.** Tatiana/ML/dataset pilots and archive (`contact_master`) lane.

| Area | Examples | Mutates? | When to use |
|------|----------|----------|-------------|
| `scripts/tatiana/*` | Drafting, pilot batch, eval | Reports / API | Tatiana pilot — [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md) |
| `scripts/dataset/*` | Tatiana cohort exports | Reports | Cohort definition / review |
| `scripts/ml/*` | `explore_email_clusters.py`, reports | Reports | ML exploration — [`REPORTING.md`](REPORTING.md) |
| `scripts/leads/campaigns/*` | DR50 reconcile, ready8 patch | Reports / CSV | Niche campaign replay — not current policy |
| `scripts/leads/build_archive_send_batch.py` | Archive send batch (`contact_master`) | Reports | Archive lane batch |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | Archive commercial precheck | Reports | Archive lane prep |
| `scripts/leads/advanced/prepare_active_workspace.py` | Hunt-sheet / `active/` hygiene | Reports | **Lead reporting** — not `prepare_outbound_campaign_workspace` |

**Removed (do not run):** Phase 5A/5C/5D/5K/5Q/5R/5S paths — see [`SCRIPT_MAP.md`](SCRIPT_MAP.md#deprecated--historical-paths-deprecated).

---

## Related

- [`SCRIPT_MAP.md`](SCRIPT_MAP.md) — full index, tags, removed phases  
- [`RUNBOOK.md`](RUNBOOK.md) — procedures, health matrix, ingest  
- [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md) — lane semantics
