# Script consolidation — conservative next steps

**Status:** planning only (no moves, deletes, import rewrites, or behavior changes implied by this document)  
**Owner:** email-pipeline-maintainers  
**Last reviewed:** 2026-05-14  
**Evidence:** `uv run python scripts/qa/plan_script_consolidation.py` (exit 0), [`docs/SCRIPT_MAP.md`](../SCRIPT_MAP.md), [`docs/RUNBOOK.md`](../RUNBOOK.md), [`tests/test_operator_entrypoint_contracts.py`](../../tests/test_operator_entrypoint_contracts.py), [`tests/test_critical_script_paths.py`](../../tests/test_critical_script_paths.py), [`docs/audits/POSTGRES_API_PIPELINE_MESS_AUDIT.md`](POSTGRES_API_PIPELINE_MESS_AUDIT.md).

---

## 1. Executive summary

### What is actually messy?

- **Volume of entrypoints:** ~**145** Python files under `scripts/` (per `plan_script_consolidation.py`). Many are **maintenance**, **lab**, or **one-off** paths that sit beside **daily outbound** scripts without a single executable “app” shell.
- **Overlapping operator stories:** Two **workspace prep** flows, **archive vs precision vs volume** lanes, several **export** scripts whose names all sound like “lists of emails,” and **root vs `leads/advanced/`** paths for the same lead-account tools.
- **Heuristic planner gaps:** The consolidation planner labels **`maintenance/dedupe_canonical_gmail_messages.py`** and **`qa/validate_contacted_csv_coverage.py`** as `unknown` because their `SCRIPT_MAP.md` table rows use tags outside the strict `OPS_*` token pattern the planner parses (e.g. markdown-bold tags). They are **documented** and **safety-relevant** — not orphan code.

### What is not messy?

- **Operator truth hierarchy** is clear: [`docs/SCRIPT_MAP.md`](../SCRIPT_MAP.md) + [`docs/RUNBOOK.md`](../RUNBOOK.md) are explicit and cross-linked.
- **Safety-critical surface** is enumerated under **Do not remove** in `SCRIPT_MAP.md` (gate, Sent history, DNR, sidecars).
- **Contracts:** [`tests/test_operator_entrypoint_contracts.py`](../../tests/test_operator_entrypoint_contracts.py) pins `--help` for daily/planner CLIs and safety headers for break-glass paths; [`tests/test_critical_script_paths.py`](../../tests/test_critical_script_paths.py) pins critical paths against accidental moves.
- **Core business logic** lives in `src/origenlab_email_pipeline/`; most scripts are thin CLIs.

### What should not be touched yet?

- **`candidate_export_gate`**, **`outbound_sent_preflight`**, **`outreach_contact_state`**, **`contact_email_suppression`**, and **Gmail Sent ingest** semantics — no consolidation PR should touch these until a dedicated, tested change.
- **Postgres migrate loaders** (`scripts/migrate/*`) — optional, break-glass; behavior and URL resolution are documented; do not “simplify” by merging into unrelated tools.
- **Compatibility root wrappers** — **removed Phase 5B (2026-06-02).** Use `scripts/leads/advanced/…` only; `test_lead_compatibility_wrappers.py` locks removal.

---

## 2. Daily core scripts (`KEEP_DAILY`)

**Definition:** On the **two outbound lanes** (volume + precision), **weekly safety refresh**, **Gmail→SQLite ingest**, or **research automation** cadence explicitly called out in `SCRIPT_MAP.md` **Ops — daily lane scripts** and/or [`RUNBOOK.md`](../RUNBOOK.md) daily / refresh sections.

| Path | Role |
|------|------|
| `scripts/qa/export_do_not_repeat_master.py` | DNR / DeepSearch input |
| `scripts/qa/export_outreach_contacted_all.py` | Auxiliary contacted-all export |
| `scripts/qa/refresh_outbound_safety_memory.py` | One-command anti-repeat refresh chain |
| `scripts/qa/validate_campaign_csvs.py` | CSV contract validation |
| `scripts/leads/process_broad_marketing_contacts.py` | Volume lane processor |
| `scripts/leads/run_current_campaign_pipeline.py` | Precision lane orchestrator |
| `scripts/qa/prepare_outbound_campaign_workspace.py` | `active/current` workspace prep (outbound lanes) |
| `scripts/leads/export_lead_contact_research_queue.py` | Precision research queue export |
| `scripts/leads/export_next_marketing_recipients.py` | Lead lane `send_ready.csv` |
| `scripts/leads/mark_sent_batch_contacted.py` | Post-send SQLite sidecar updates |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Gmail → `emails` (Sent / inbox) |
| `scripts/research/run_deep_research_prospecting.py` | Research automation (no send); **cadence** heavy vs light — still `OPS_DAILY` in map |

**Also treat as `KEEP_DAILY` for the anti-repeat sequence (RUNBOOK):**

| Path | Role |
|------|------|
| `scripts/qa/export_all_known_marketing_contacts.py` | Dedup “all known” marketing contacts export |
| `scripts/qa/validate_contacted_csv_coverage.py` | Strict coverage check in refresh sequence |

**Operator `--help` contract (must stay stable):** the tuple in `tests/test_operator_entrypoint_contracts.py::_HELP_ENTRYPOINTS` (subset of the above + planners + `archive_reports_out_generated.py`).

### Lead-account scripts (**removed Phase 5B root wrappers**)

Canonical implementations only under `scripts/leads/advanced/`. Root-level `scripts/build_lead_account_rollup.py` (+ three siblings) were **removed in Phase 5B** — see [`scripts/README.md`](../../scripts/README.md) and `test_lead_compatibility_wrappers.py`.

---

## 3. Core support scripts (`KEEP_CORE` / `KEEP_MAINTENANCE`)

### `KEEP_CORE` (operator-regular; not every send)

| Path | Notes |
|------|--------|
| `scripts/leads/import_lead_contact_research_csv.py` | Precision lane DB apply — **`--apply`** gated (`SCRIPT_MAP`: OPS_CORE) |
| `scripts/leads/import_operator_outreach_blocklist.py` | Blocklist |
| `scripts/leads/add_manual_contact_suppressions.py` | Manual suppressions |
| `scripts/leads/mark_outreach_state.py` | Manual `outreach_contact_state` edits |
| `scripts/leads/build_archive_send_batch.py` | Archive lane batch |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | Archive commercial precheck |
| `scripts/qa/prepare_outbound_campaign_workspace.py` | Already daily table — also **core** workspace reset |

### `KEEP_MAINTENANCE` (rebuilds, commercial, reports, ingest utilities, lead pipeline depth)

Representative families (not exhaustive; see `SCRIPT_MAP` **Archive lane & maintenance**, `scripts/README.md` folder map, planner bucket `maintenance: 59`):

- **Mart / commercial:** `scripts/mart/build_business_mart.py`, `scripts/commercial/build_commercial_intel_v1.py`, `scripts/commercial/*` review/export helpers.
- **Reports:** `scripts/reports/*`, `scripts/mart/open_client_report.py`.
- **Ingest (non-daily):** `scripts/ingest/02_mbox_to_sqlite.py`, `03_sqlite_to_jsonl.py`, `04_imap_to_sqlite.py`, etc.
- **Lead pipeline:** `scripts/leads/normalize_leads.py`, scoring, ChileCompra fetches, `match_leads_to_mart.py`, dedupe, `run_weekly_focus.py`, …
- **Maintenance / corrective:** `scripts/maintenance/dedupe_canonical_gmail_messages.py` (**break-glass** in `SCRIPT_MAP`; planner `unknown` = tag parse quirk).

---

## 4. Audit / read-only scripts (`KEEP_AUDIT`)

Planner bucket **`audit_readonly: 23`**; `SCRIPT_MAP` **Ops — audit & debug (OPS_AUDIT)** table lists the canonical set. Examples:

- `scripts/qa/export_gate_audit_csv.py`, `export_contacted_lead_overlap_audit.py`, `export_supplier_domain_false_positive_audit.py`, `export_outreach_volume_rollup.py`
- `scripts/qa/check_outbound_readiness.py`, `check_reports_out_active_hygiene.py`, `check_reproducibility.py`
- `scripts/qa/audit_canonical_contacto_gmail.py`, `audit_canonical_gmail_duplicates.py`
- `scripts/qa/validate_sqlite_archive_for_postgres.py` (read-only; also **pre-migrate**)
- `scripts/qa/publish_gate.py`, `audit_operational_trust.py`, `verify_client_pack_consistency.py`, `plan_*`, `print_outbound_run_summary.py`, `export_candidate_audit.py`

**Special:** `scripts/leads/backfill_contacted_from_gmail_sent.py` — **dry-run default**; `--apply` mutates — treat as **audit-first**, break-glass when applying.

**Planners (no file mutations):** `plan_script_consolidation.py`, `plan_reports_out_cleanup.py`, `plan_source_quality.py` → **`KEEP_AUDIT`** (planning / inspection).

---

## 5. Migration scripts (`KEEP_MIGRATION`)

**Optional Postgres path only** — SQLite remains operational OLTP ([`POSTGRES_API_PIPELINE_MESS_AUDIT.md`](POSTGRES_API_PIPELINE_MESS_AUDIT.md), `RUNBOOK.md` § Optional PostgreSQL).

| Path | Risk |
|------|------|
| `scripts/migrate/sqlite_archive_to_postgres.py` | **TRUNCATE**/load archive |
| `scripts/migrate/sqlite_document_master_to_postgres.py` | **DELETE**/load |
| `scripts/migrate/sqlite_outbound_sidecars_to_postgres.py` | **DELETE**/load |

**Operator rule:** do **not** run casually; **scratch Postgres first**; use `validate_sqlite_archive_for_postgres.py --strict` before loads.

---

## 6. Experimental / lab scripts (`KEEP_EXPERIMENTAL`)

Planner bucket **`lab_archive: 20`**; `SCRIPT_MAP` **Lab scripts (LAB)**:

- `scripts/tatiana/*` — drafting / pilot / eval (see `TATIANA_LAB_BOUNDARY.md`)
- `scripts/dataset/*` — cohorts, labels, Tatiana metrics
- `scripts/ml/*` — embeddings / clusters
- `scripts/leads/campaigns/*` — DR50 / cohort reconcilers
- Much of `scripts/leads/advanced/*` except shared operational paths — **contact hunt**, **prepare_active_workspace** (legacy weekly lead focus), **`run_contact_hunt_web_server.py`** (local CSV HTTP server)

---

## 7. Archive candidates (`ARCHIVE_CANDIDATE`)

**None with strong evidence for code archival or deletion.** Reasons:

- Paths under **`test_critical_script_paths`** or **`_HELP_ENTRYPOINTS`** / **`_BREAK_GLASS_PATHS`** must not be archived on speculation.
- **Campaign-specific** scripts remain valuable as **historical reproducibility** for past cohorts; archival is a **process** (move old `reports/out` artifacts), not deleting `scripts/leads/campaigns/*.py`.

**`REVIEW_LATER` (weak signal, not archive):**

- After a campaign is fully closed **and** docs no longer reference a script, re-run `plan_script_consolidation.py` and grep docs/tests — only then consider **archive** (still not delete without ADR).

---

## 8. Duplicate or confusing stories

| Topic | Paths / evidence | Clarification |
|------|------------------|---------------|
| **Two workspace prep stories** | `scripts/qa/prepare_outbound_campaign_workspace.py` vs `scripts/leads/advanced/prepare_active_workspace.py` | `SCRIPT_MAP` **Two workspace prep stories**: first = **two daily outbound lanes** + `active/current`; second = **legacy weekly lead focus** / hunt / `REPORTING.md`. |
| **Root wrappers vs advanced** | ~~`scripts/build_lead_account_rollup.py`~~ → `scripts/leads/advanced/build_lead_account_rollup.py` (+ 3 siblings) | **Removed Phase 5B** — canonical paths only under `leads/advanced/`; [`scripts/README.md`](../../scripts/README.md) documents the family. |
| **Campaign-specific** | `scripts/leads/campaigns/*` | Lab/cohort tooling; not daily lanes; keep README [`scripts/leads/campaigns/README.md`](../../scripts/leads/campaigns/README.md) as context. |
| **Overlapping RUNBOOK names** | `export_do_not_repeat_master` vs `export_outreach_volume_rollup` vs `export_outreach_contacted_all` vs `export_all_known_marketing_contacts` | `SCRIPT_MAP` **Overlap note:** DNR **input list** vs **saturation metrics** vs **contacted-all** vs **all-known dedup** — different jobs. |
| **Sounds like “send prep”** | `scripts/leads/build_manual_html_outreach_batch.py` vs `scripts/qa/send_inline_html_email_via_gmail_api.py` | HTML package **files** vs **break-glass** Gmail API send. |
| **Planner “unknown” ≠ orphan** | `dedupe_canonical_gmail_messages.py`, `validate_contacted_csv_coverage.py` | Documented in `SCRIPT_MAP` / RUNBOOK; planner regex misses bold tag column. |

---

## 9. Top 10 confusion points

| # | Script / path | Why it confuses | Dangerous? | Recommended next action |
|---|----------------|-----------------|------------|-------------------------|
| 1 | `prepare_outbound_campaign_workspace.py` vs `leads/advanced/prepare_active_workspace.py` | Same word “prepare”, different `reports/out` contract | Low if read doc; wrong folder = **wasted work** | Doc PR: one diagram + link both in `scripts/README` “Quick navigation” |
| 2 | ~~Root `scripts/match_lead_accounts_to_existing_orgs.py`~~ vs `leads/advanced/…` | Was duplicate shim; **removed Phase 5B** | Low | Use `scripts/leads/advanced/…` only |
| 3 | `export_all_known_marketing_contacts` vs `export_outreach_contacted_all` | Both “big lists” | Low | Table in internal wiki / `SCRIPT_INVENTORY` row already; optional RUNBOOK callout box |
| 4 | `export_do_not_repeat_master` vs `export_outreach_volume_rollup` | “Export” + outreach words | Low | Already in `SCRIPT_MAP` overlap note — link from `scripts/README` DNR paragraph |
| 5 | `run_deep_research_prospecting.py` tagged `OPS_DAILY` | Heavy mode is weekly; “daily” overload | Medium if run heavy on laptop | Doc: clarify **cadence** in RUNBOOK research subsection only |
| 6 | `import_lead_contact_research_csv.py` | Precision-only; volume must not misuse | **High** if mis-imported | Keep gate docs; no script merge |
| 7 | `backfill_contacted_from_gmail_sent.py` vs `mark_sent_batch_contacted.py` | Both touch contacted state | **Medium** with `--apply` | Doc: side-by-side table (batch mark vs Sent backfill) in `LEAD_PIPELINE.md` |
| 8 | `build_archive_send_batch.py` vs `export_next_marketing_recipients.py` | Both produce send-related CSVs | Medium | `SCRIPT_MAP` ARCHIVE_LANE vs lead lane — add RUNBOOK anchor cross-link only |
| 9 | `sync_outreach_batch_from_ingested_bounces.py` | Sounds like refresh; **`--apply`** mutates | **High** | Keep break-glass; no merge; RUNBOOK already positions NDR — optional “when to use” bullet |
|10 | `plan_script_consolidation` output `unknown` | Looks like “delete me” | Low (misleading) | Doc PR: normalize `SCRIPT_MAP` table tag cells to plain `OPS_*` / `BREAK_GLASS` tokens **or** extend planner regex — **behavior unchanged** |

---

## 10. First 3 safe cleanup PRs (small, doc-first)

### PR A — Fix broken lead-account links in `scripts/README.md`

| | |
|--|--|
| **Status** | **Done** (2026-06) — quick navigation table uses `leads/advanced/…` paths. |

### PR B — Workspace prep “pick one” callout

| | |
|--|--|
| **Files** | `apps/email-pipeline/docs/SCRIPT_INVENTORY.md` and/or `apps/email-pipeline/docs/leads/LEAD_PIPELINE.md` (pick one place operators open) |
| **Behavior** | None |
| **Tests** | `uv run pytest -q` (full suite optional); link check manual |
| **Rollback** | Revert doc commit |

**Change:** Short subsection: **when** `prepare_outbound_campaign_workspace` vs `prepare_active_workspace`; link `SCRIPT_MAP` anchor **Two workspace prep stories**.

### PR C — Link this plan from the doc index

| | |
|--|--|
| **Files** | `apps/email-pipeline/docs/README.md` (audits / agent-first list) **or** `apps/email-pipeline/docs/SCRIPT_INVENTORY.md` |
| **Behavior** | None |
| **Tests** | None required |
| **Rollback** | Revert doc commit |

**Change:** One bullet pointing to **`docs/audits/SCRIPT_CONSOLIDATION_NEXT_STEPS.md`** next to `plan_script_consolidation.py` mention.

**Optional follow-up (separate PR, only if agreed):** normalize `SCRIPT_MAP.md` table tag cells so `plan_script_consolidation.py` stops marking `dedupe_canonical_gmail_messages.py` / `validate_contacted_csv_coverage.py` as `unknown` — **documentation / parser alignment**; no script behavior change.

---

## Appendix — `plan_script_consolidation.py` snapshot (2026-05-14)

```
total .py under scripts/: 145
compatibility_wrapper=4 | unknown=2 | break_glass=18
--- by bucket ---
  maintenance: 59
  audit_readonly: 23
  lab_archive: 20
  break_glass: 18
  daily: 11
  compatibility_wrapper: 4
  core_operator: 4
  migration: 3
  unknown: 2
  infrastructure_core: 1
```

Suggested planner tail (verbatim): triage `unknown` with owners; **do not remove** compatibility wrappers until paths migrate; re-run planner after doc/script renames.
