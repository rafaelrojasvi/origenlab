# Unknown-review surface classification — 2026-06-05

Status: read-only audit (docs only)  
Branch context: clean `main` after planner v2 (#100 planning)  
Sources: `reports/local/function-surface-audit-v2-smoke/*`, `reports/local/import-surface-audit-smoke/*`, `docs/SCRIPT_MAP.md`, `docs/OPERATOR_COMMAND_SURFACE.md`

**This document is not deletion authority.** Planner buckets and import counts are heuristics. Zero references do not prove a file is safe to remove. Confirm with owners, tests, and `uv run origenlab audit-facades` before any move or delete.

---

## 1. Executive summary

The function-surface planner labeled **118** Python files as `unknown_review` (29,746 LOC total). After cross-checking import/reference evidence and existing audits, manual classification yields:

| Classification | Files | Approx. LOC | Verdict |
|----------------|------:|------------:|---------|
| **active_core** | 62 | ~14,800 | Keep — infrastructure, read modules, schema, high fan-in |
| **read_only_report** | 28 | ~5,900 | Keep — QA, client/campaign reports, operator status backing |
| **outbound_or_send_adjacent** | 9 | ~3,500 | Freeze safety path — archive/outbound lane writers |
| **postgres_or_mirror_adjacent** | 7 | ~3,400 | Freeze unless mirror work — Postgres sync/migrate |
| **legacy_manual** | 4 | ~2,200 | Document / break-glass — legacy ingest, campaign one-offs |
| **break_glass_dangerous** | 4 | ~650 | Freeze — Gmail dedupe, attachment rebuild, `reports_out` purge paths |
| **parked_lab** | 2 | ~1,930 | Park or document — research automation, lab buyers |
| **needs_owner_review** | 2 | ~443 | Assign owner before any cleanup PR |

**Answers to planning questions:**

| Question | Answer |
|----------|--------|
| Which unknown files are actually **active**? | **62** `active_core` modules (`config.py`, `db.py`, `read/*`, catalog, equipment, NDR helpers, package inits). Highest fan-in: `config` (260 refs), `db` (202), `leads_schema` (107). |
| Which are **read-only reports**? | **28** — client report stack, campaign QA/templates, `operator_status_report.py`, classification QA, ML report script. |
| Which are **parked/lab**? | **2** large — `core/research_automation.py` (1,683 LOC), `chilecompra_licitacion_lab_buyers.py`. Treat as non-daily lane per `TATIANA_LAB_BOUNDARY.md` / research docs. |
| Which need **SCRIPT_MAP** entries? | **`scripts/reports/*`** (5 scripts) — added in this PR. Ops/maintenance scripts mostly already mapped. |
| Which are **dangerous / frozen**? | Postgres mirror/migrate stack, Gmail dedupe maintenance, `core/reports_out.py` (archive purge semantics), `extract_attachment_text.py` rebuild. |
| **Possible deletion candidates?** | **None recommended from this audit alone.** Lowest-ref large files (`equipment_deepsearch_vetted_queue.py` 8 refs, `attachment_extract.py` 4 refs) still have operational or break-glass roles. Facade stubs (`core/db.py`, `core/gmail/contacto_gmail_source.py`) with 0 direct import edges are **not** delete candidates. |
| **Best next PR after classification?** | **Re-tag planner `classify_likely_bucket()`** for the 118 paths (docs + small planner patch + tests) so future runs land in real buckets — **no file moves**. Optional follow-up: campaign one-off retirement doc cross-links only. |

---

## 2. Methodology

1. Pulled `unknown_review` rows from `module_inventory.csv` (function surface planner v2 smoke).
2. Joined `python_import_count` / `total_references` from import-surface planner.
3. Cross-checked `risk_bucket`, facade pairs (99 modules repo-wide), and existing audits (`ROOT_MISC_MODULE_CLASSIFICATION_20260604.md`, `CAMPAIGN_ONEOFF_RETIREMENT_AUDIT_20260602.md`).
4. Assigned one **classification** per file; **safe next action** is planning-only.

**Not in scope:** running scripts, SQLite/Postgres/Gmail mutations, refactors, or deletes.

---

## 3. Top 30 unknown-review files by LOC

| path | LOC | fn | pub fn | risk | refs | likely owner | classification | safe next action | do not do |
|------|----:|---:|-------:|------|-----:|--------------|----------------|------------------|-----------|
| `src/.../core/research_automation.py` | 1683 | 40 | 19 | read_only | 28 | research / DeepSearch lane | parked_lab | Document in `TATIANA_LAB_BOUNDARY`; keep out of daily refresh | Do not fold into outbound or delete on low refs |
| `src/.../mart_core_postgres_migrate.py` | 1181 | 42 | 33 | postgres_mirror | 129 | postgres mirror | postgres_or_mirror_adjacent | Freeze unless mirror migration PR | No `alembic upgrade` / mirror `--apply` in cleanup |
| `scripts/reports/generate_client_report.py` | 1111 | 9 | 6 | writes_sqlite | 22 | client reports | read_only_report | SCRIPT_MAP row added; keep for client packs | Not send approval; not deletion candidate |
| `src/.../dashboard_postgres_sync.py` | 1048 | 32 | 28 | postgres_mirror | 32 | postgres mirror | postgres_or_mirror_adjacent | Freeze; use `origenlab mirror-dashboard` dry-run only | No production Postgres writes from audit work |
| `src/.../archive_outreach_queue.py` | 803 | 28 | 8 | writes_sqlite | 36 | outbound archive | outbound_or_send_adjacent | Characterize with archive lane tests | No send / export gate changes |
| `src/.../campaigns/presentacion_origenlab_quality.py` | 785 | 15 | 2 | unknown_review | 14 | campaign one-off | read_only_report | Keep for presentation campaign round | See `CAMPAIGN_ONEOFF_RETIREMENT_AUDIT` |
| `src/.../email_classification_qa.py` | 767 | 24 | 19 | writes_sqlite | 38 | qa / classification | read_only_report | Keep tests; used by classification audits | Do not wire to send gates |
| `src/.../campaigns/cyber_outreach_campaign.py` | 691 | 13 | 2 | writes_sqlite | 13 | campaign one-off | legacy_manual | Characterize before any retirement | No delete without campaign audit sign-off |
| `src/.../campaigns/cyber_campaign_context_audit.py` | 676 | 17 | 6 | writes_sqlite | 30 | campaign QA | read_only_report | Keep as read-only campaign audit | Reports only |
| `src/.../campaigns/cyber_campaign_quality.py` | 669 | 19 | 13 | writes_sqlite | 32 | campaign QA | read_only_report | Keep as read-only campaign audit | Reports only |
| `src/.../campaigns/presentacion_origenlab_campaign.py` | 646 | 15 | 6 | unknown_review | 22 | campaign one-off | legacy_manual | Characterize before retirement | No delete without proof |
| `src/.../equipment_deepsearch_vetted_queue.py` | 644 | 18 | 9 | writes_sqlite | 8 | equipment-first | active_core | Add equipment lane doc pointer | Low refs ≠ delete (equipment lane active) |
| `src/.../campaigns/presentacion_origenlab_presend_audit.py` | 632 | 10 | 3 | unknown_review | 18 | campaign QA | read_only_report | Keep for presend audit | Read-only |
| `src/.../archive_send_batch_builder.py` | 608 | 16 | 4 | writes_sqlite | 39 | outbound archive | outbound_or_send_adjacent | Freeze safety path | No send batch changes |
| `src/.../validation/attachment_validation.py` | 533 | 4 | 4 | writes_sqlite | 11 | validation | active_core | Keep with attachment pipeline docs | — |
| `src/.../campaigns/post_send_digest.py` | 532 | 8 | 5 | writes_sqlite | 2 | campaigns (not CLI digest) | legacy_manual | Distinguish from `origenlab post-send-digest` | Do not merge/delete vs QA digest without owner |
| `src/.../equipment_opportunity_mirror.py` | 517 | 21 | 15 | postgres_mirror | 9 | equipment + mirror | postgres_or_mirror_adjacent | Freeze unless mirror work | — |
| `src/.../equipment_first_licitacion_queue.py` | 473 | 12 | 10 | read_only | 30 | equipment-first | active_core | Keep — licitacion queue | — |
| `scripts/reports/build_leads_client_pack.py` | 458 | 6 | 2 | writes_sqlite | 11 | client reports | read_only_report | SCRIPT_MAP row added | Reports under `reports/out` only |
| `src/.../parse_mbox.py` | 441 | 18 | 13 | read_only | 63 | legacy ingest | legacy_manual | Document as non-daily ingest | Do not promote to daily Gmail path |
| `src/.../catalog/catalog_builder.py` | 440 | 4 | 3 | writes_sqlite | 7 | catalog | active_core | Document in catalog section | — |
| `src/.../operator_status_report.py` | 440 | 17 | 10 | postgres_mirror | 21 | operator_cli / status | read_only_report | Keep — backs `origenlab status` | No behavior change without CLI tests |
| `src/.../attachment_extract.py` | 429 | 12 | 2 | read_only | 4 | legacy ingest | legacy_manual | Break-glass ingest helper | Low refs ≠ delete |
| `src/.../read/today_workspace.py` | 418 | 15 | 5 | writes_sqlite | 41 | read / operator | active_core | Keep with dashboard read path | High coupling to active workspace |
| `src/.../email_business_filters.py` | 390 | 25 | 10 | writes_sqlite | 32 | outbound filters | outbound_or_send_adjacent | Freeze — filter semantics | No gate changes |
| `src/.../archive_shortlist_commercial_precheck.py` | 387 | 14 | 7 | writes_sqlite | 12 | outbound archive | outbound_or_send_adjacent | Freeze archive lane | — |
| `src/.../equipment_first_operator_queue.py` | 384 | 10 | 7 | writes_sqlite | 15 | equipment-first | active_core | Keep equipment lane | — |
| `src/.../client_report_metrics.py` | 366 | 6 | 6 | writes_sqlite | 22 | client reports | read_only_report | Part of client report stack | — |
| `src/.../canonical_operational_sql.py` | 357 | 18 | 17 | writes_sqlite | 26 | core SQL | active_core | Keep — shared SQL predicates | — |
| `src/.../read/leads_browse.py` | 356 | 11 | 5 | writes_sqlite | 16 | read / API | active_core | Keep with read module tests | — |

*(Full paths use prefix `src/origenlab_email_pipeline/` or `scripts/`.)*

---

## 4. High-risk unknown-review files

These have `risk_bucket` ∈ {`send_or_purge`, `gmail_ingest`, `postgres_mirror_or_migration`, `outbound_apply`}:

| path | LOC | risk | refs | classification | action |
|------|----:|------|-----:|----------------|--------|
| `mart_core_postgres_migrate.py` | 1181 | postgres_mirror | 129 | postgres_or_mirror_adjacent | Freeze |
| `dashboard_postgres_sync.py` | 1048 | postgres_mirror | 32 | postgres_or_mirror_adjacent | Freeze |
| `core/reports_out.py` | 271 | send_or_purge | 32 | break_glass_dangerous | Archive move semantics — dry-run default |
| `outreach_ingest_sync.py` | 337 | gmail_ingest | 24 | outbound_or_send_adjacent | Freeze ingest coupling |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | 201 | gmail_ingest | 13 | break_glass_dangerous | BREAK_GLASS — already in SCRIPT_MAP |
| `operator_status_report.py` | 440 | postgres_mirror | 21 | read_only_report | Keep (status CLI) |
| `operational_scope.py` | 156 | postgres_mirror | 42 | active_core | Keep — API/mirror scope (`ROOT_MISC` audit) |
| `contacto_gmail_source.py` | 93 | gmail_ingest | 81 | active_core | Facade pair root — freeze predicate changes |
| `canonical_gmail_dedupe.py` | 113 | gmail_ingest | 18 | active_core | Keep dedupe library |
| `catalog/catalog_mirror_*` | 221–183 | postgres_mirror | 9–38 | postgres_or_mirror_adjacent | Freeze mirror reads |
| `equipment_opportunity_mirror.py` | 517 | postgres_mirror | 9 | postgres_or_mirror_adjacent | Freeze |
| `scripts/ops/cloud_postgres_url.py` | 92 | postgres_mirror | 6 | postgres_or_mirror_adjacent | Keep — ops URL helper (SCRIPT_MAP) |
| `scripts/ops/refresh_operational_dashboard_stack.py` | 113 | postgres_mirror | 6 | postgres_or_mirror_adjacent | Optional stack — EXPERIMENTAL_PARKED |
| `core/gmail/contacto_gmail_source.py` | 8 | gmail_ingest | 0 | active_core | **Facade** — not delete candidate |

---

## 5. Zero-reference and low-reference notes

| Finding | Count | Notes |
|---------|------:|-------|
| Zero Python-import modules in `unknown_review` | 0 | No non-facade src module with zero import edges |
| Facade stubs with 0 import edges | 3 | `core/db.py`, `core/sqlite_migrate.py`, `core/gmail/contacto_gmail_source.py` — paired with root implementations |
| Zero doc+test script refs (repo-wide) | 10 | **None** are `unknown_review` scripts with zero refs — all 12 unknown scripts have ≥1 doc/test mention |
| Low-ref large files (LOC ≥400, refs ≤8) | 2 | `equipment_deepsearch_vetted_queue.py`, `attachment_extract.py` — **keep**, assign equipment/ingest owner |

**Do not treat zero-reference lists from `plan_import_surface.py` as deletion queues.**

---

## 6. Unknown-review scripts (12)

| script | LOC | refs | classification | SCRIPT_MAP |
|--------|----:|-----:|----------------|------------|
| `scripts/reports/generate_client_report.py` | 1111 | 22 | read_only_report | **Added** |
| `scripts/reports/build_leads_client_pack.py` | 458 | 11 | read_only_report | **Added** |
| `scripts/validation/extract_attachment_text.py` | 344 | 10 | break_glass_dangerous | Already break-glass table |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | 201 | 13 | break_glass_dangerous | Already BREAK_GLASS |
| `scripts/reports/build_ml_report.py` | 168 | 1 | parked_lab | **Added** |
| `scripts/reports/run_all_reports.py` | 125 | 2 | read_only_report | **Added** |
| `scripts/ops/refresh_operational_dashboard_stack.py` | 113 | 6 | postgres_or_mirror_adjacent | Already OPS |
| `scripts/ops/cloud_postgres_url.py` | 92 | 6 | postgres_or_mirror_adjacent | Already OPS |
| `scripts/reports/generate_business_filter_report.py` | 86 | 5 | read_only_report | **Added** |
| `scripts/validation/backfill_phase2_2_text_fields.py` | 70 | 6 | active_core | Validation backfill — keep |
| `scripts/_bootstrap.py` | 18 | 3 | active_core | Internal — not operator entry |
| `scripts/_script_warnings.py` | 14 | 2 | active_core | Internal — not operator entry |

---

## 7. Needs owner review (2)

| path | LOC | refs | issue | safe next action |
|------|----:|-----:|-------|------------------|
| `src/.../ndr_bounce_extraction.py` | 236 | 19 | NDR helper; overlaps bounce/NDR lanes | Assign to NDR owner; add PACKAGE_DOMAINS row |
| `src/.../manual_html_outreach_batch.py` | 207 | 20 | Manual HTML send path library | Confirm break-glass status with outbound owner |

*(Previously misc bucketed: `operator_copy_es.py`, `catalog/catalog_seed.py` — classify as **active_core** / catalog on second pass.)*

---

## 8. Recommended next PR (after this doc)

1. **Planner bucket re-tag PR (small, safe):** Extend `classify_likely_bucket()` in `plan_function_surface.py` with rules for campaigns, equipment, catalog, read, reports, postgres mirror filenames — **reduces false `unknown_review` count** without moving files.
2. **Docs-only cross-links:** Point `PACKAGE_DOMAINS.md` at this audit for the 2 `needs_owner_review` modules.
3. **Defer:** Any file deletion, campaign retirement, or warm-case split — requires proof from **both** planners + targeted tests.

---

## 9. Safety

- Read-only documentation derived from local planner smoke outputs.
- No SQLite / Postgres / Gmail / send / purge / mirror operations performed for this audit.
