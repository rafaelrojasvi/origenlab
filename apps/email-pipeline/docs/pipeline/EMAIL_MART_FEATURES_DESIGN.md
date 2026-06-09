# Precomputed email mart features (design)

Status: design only (not implemented)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-09

Related: [`BUSINESS_MART.md`](BUSINESS_MART.md) · [`DAILY_CORE.md`](DAILY_CORE.md) · [`DAILY_CORE_FAST_REFRESH_SPLIT.md`](DAILY_CORE_FAST_REFRESH_SPLIT.md) · [`MART_FRESHNESS.md`](MART_FRESHNESS.md)

This document proposes a **precomputed per-email feature table** in SQLite so mart rebuilds can aggregate from stable features instead of re-reading and materializing `top_reply_clean` for every row on every full scan.

**Scope:** design and operator expectations only. It does **not** change `daily-core`, `build-mart`, Gmail ingest, Postgres mirror, send, purge, NDR apply, Alembic, or dashboard behavior.

---

## 1. Problem statement

Today, `build-mart -- --rebuild` drives `scan_email_contacts()` in `contact_org_builder.py`, which:

1. Executes a full-table `SELECT` over `emails` including `COALESCE(top_reply_clean,'')`.
2. Fetches rows in batches via `fetchmany(5000)`.
3. For each row, runs noise filtering, intent classification, equipment tagging, and contact/org rollups.

Profiling PRs #154–#159 showed that **SQLite fetch and text materialization dominate** runtime. Measured Python stages (intent, equipment, address parse, etc.) explain only a small fraction of `email_scan_seconds`. Target-gated body fetch (skipping body for rows with no external contact targets) would save only a modest slice because **most scanned body chars belong to pre-noise target candidates**.

The real cost is **re-materializing ~285M characters from SQLite on every full mart rebuild**, then re-running the same per-email derivations from scratch.

**Design goal:** compute expensive per-email features once, store them in SQLite, and rebuild `contact_master` / `organization_master` / `opportunity_signals` by aggregating features — with full backfill, incremental update, and parity proof before any daily-core switch.

---

## 2. Evidence (production profile)

Latest production `build-mart -- --rebuild` run after PRs #154–#159 (SQLite mailbox ~217k `emails` rows):

| Metric | Value | Notes |
|--------|-------|-------|
| Scanned rows | 217,100 | Full email scan |
| `email_scan_seconds` | 354.06 | Mart contact scan stage |
| `mart_scan_fetchmany_seconds` | 318.38 | ~90% of `email_scan_seconds` |
| `mart_scan_measured_stage_seconds` | ~35 | Sum of timed Python stages |
| `body_total_chars` | 284,639,951 | All materialized body text |
| `mart_pre_noise_target_candidate_body_chars` | 263,752,022 | ~92.7% of body chars |
| `mart_pre_noise_no_target_body_chars` | 20,887,929 | ~7.3% of body chars |
| `mart_scan_equipment_seconds` | ~29.8 | Largest Python stage |
| `mart_scan_intent_seconds` | ~2.4 | Second-largest Python stage |

**Prior optimization series (context):**

| PR | Finding |
|----|---------|
| #154 | `full_body_clean` fallback unused in production |
| #155 | Lazy `full_body_clean` saved only ~20s |
| #156 | Measured Python stages ≈ 35s of ~360s scan |
| #157 | `fetchmany` ≈ 90% of scan time |
| #158 / #159 | Pre-noise no-target body ≈ 7.3%; target gate alone ≈ 20–25s savings estimate |

**Conclusion:** Target-gated body fetch is a small win. **Precomputed features + incremental maintenance** is the path to materially faster mart rebuilds and future fast-refresh lanes.

---

## 3. Proposed table: `email_mart_features`

SQLite table (via `sqlite_migrate` layer — **not** Alembic, **not** Postgres mirror in first PR).

| Column | Type (suggested) | Purpose |
|--------|------------------|---------|
| `email_id` | INTEGER PRIMARY KEY | FK to `emails.id` |
| `message_id` | TEXT | Source `emails.message_id` for audit / incremental matching |
| `source_file` | TEXT | Optional; canonical Gmail source path |
| `folder` | TEXT | Optional; INBOX / Sent folder label |
| `sender_email` | TEXT | Parsed primary sender |
| `sender_domain` | TEXT | `domain_of(sender_email)` |
| `recipient_emails_json` | TEXT | JSON array of parsed recipient emails |
| `external_targets_json` | TEXT | JSON array of external contact targets (same rules as scan) |
| `direction` | TEXT | `inbound` / `outbound` / `other` |
| `is_noise` | INTEGER | 0/1 — result of `is_noise_sender` |
| `is_quote_email` | INTEGER | 0/1 |
| `is_invoice_email` | INTEGER | 0/1 |
| `is_purchase_email` | INTEGER | 0/1 |
| `equipment_tags` | TEXT | Comma-separated or JSON array of equipment tags |
| `has_business_doc` | INTEGER | Optional; 0/1 from `doc_aggs` at compute time |
| `quote_doc_count` | INTEGER | Optional; from `doc_aggs` — may stay separate |
| `invoice_doc_count` | INTEGER | Optional; from `doc_aggs` — may stay separate |
| `mart_date_iso` | TEXT | Normalized timeline date (`email_date_iso_for_mart_timeline`) |
| `body_len` | INTEGER | Length of body used for classification (no body text stored) |
| `feature_source_hash` | TEXT | Hash of inputs that invalidate features (see below) |
| `computed_at` | TEXT | ISO timestamp when row was written |

**Not stored in v1:** raw `top_reply_clean` / `full_body_clean` (features table is derived, not a body cache).

**`feature_source_hash` inputs (draft):** `message_id`, `sender`, `recipients`, `subject`, `top_reply_clean` length + hash or prefix hash, `date_iso`, internal-domain config version, classifier version string. Exact hash contract to be fixed in PR B.

**Doc counts:** `has_business_doc` / `quote_doc_count` / `invoice_doc_count` depend on `document_master` / `doc_aggs`. Options:

- Compute during feature extraction when doc tables are available (simplest parity).
- Or leave doc fields NULL in features and join at rollup time (second phase).

Prefer **compute with doc_aggs** for parity with current scan; document that incremental doc changes may require feature recomputation for affected `email_id`s.

---

## 4. Build modes

### 4.1 Full backfill

- Read all qualifying `emails` rows (same WHERE semantics as current scan: canonical source, `since_days` when used).
- For each row: parse addresses, classify noise/intent/equipment, resolve targets, write or replace `email_mart_features`.
- Profile-only / dry-run mode prints row counts and timing without writing.

### 4.2 Incremental update

- After Gmail ingest or on demand: select emails where:
  - no `email_mart_features` row exists, or
  - `feature_source_hash` differs from stored hash.
- Recompute features only for that delta set.
- Does **not** imply incremental `contact_master` until PR D/E parity is proven.

### 4.3 Rebuild contact/org from features

- New aggregation path: scan `email_mart_features` (not `emails.top_reply_clean`).
- Apply same rollup rules as `scan_email_contacts()` → `contact` map → `rebuild_contact_master` / org / opportunity builders.
- Behind a flag until parity audit passes.

---

## 5. Safety and parity plan

**Principle:** observability and proof before any daily-core semantic change.

| Phase | Activity |
|-------|----------|
| Initial command | **Dry-run / profile only** — counts, timing, hash misses; no mart table writes |
| Fixture parity | Compare old scan vs feature-based outputs on in-memory SQLite fixtures (contacts, orgs, intents, equipment) |
| Production audit | Compare aggregate counts: `contact_master`, `organization_master`, `opportunity_signals` row counts |
| Sampled diff | Spot-check sampled contacts/orgs (email, domain, counts, top equipment tags) |
| Stable export | Optional checksum or deterministic CSV diff of mart tables (sorted keys) |

**Rollback:** keep existing `scan_email_contacts()` path until PR F; feature path is additive behind flag.

**Operator safety (unchanged):**

- Feature backfill does not send mail, purge data, apply NDR, or write Postgres.
- `daily-core` continues to use current scan until explicit switch PR.

---

## 6. Migration plan

1. **Schema:** add `email_mart_features` through `sqlite_migrate` (same pattern as other SQLite mart tables). No Alembic migration in v1.
2. **No Postgres mirror changes** in first implementation PRs — mirror continues to reflect existing mart tables after rebuild.
3. **Versioning:** bump classifier version in hash when `business_mart` rules change; document operator note to run full backfill after rule changes.
4. **Storage:** table is rebuildable from `emails` + `document_master`; safe to truncate and backfill.

---

## 7. Non-goals

- Do **not** change `daily-core` semantics in early PRs.
- Do **not** remove or bypass existing `scan_email_contacts()` until parity is proven.
- Do **not** change Gmail ingest, send, purge, NDR apply, Alembic, or dashboard write paths.
- Do **not** mirror `email_mart_features` to Postgres in v1.
- Do **not** implement fast-refresh CLI in this series (see [`DAILY_CORE_FAST_REFRESH_SPLIT.md`](DAILY_CORE_FAST_REFRESH_SPLIT.md)) — features enable it later.

---

## 8. Proposed PR sequence

| PR | Scope | Wired to daily-core? |
|----|-------|----------------------|
| **A** | This design doc only | No |
| **B** | Schema (`email_mart_features`) + feature extraction helpers + unit tests | No |
| **C** | Backfill / profile CLI command (dry-run default) | No |
| **D** | Feature-based contact/org builder behind `--use-mart-features` (or env flag) | No |
| **E** | Parity audit command + fixture/production diff reports | No |
| **F** | Switch `build-mart` / `daily-core` to feature path **only after** parity sign-off | Yes (explicit) |

Each PR should remain independently reviewable; B–E must not alter default mart output.

---

## 9. Relationship to fast refresh

[`DAILY_CORE_FAST_REFRESH_SPLIT.md`](DAILY_CORE_FAST_REFRESH_SPLIT.md) documents why per-email automation cannot call full `build-mart -- --rebuild` today. Precomputed features are the likely foundation for:

- incremental feature updates after partial Gmail ingest, and
- aggregating recent operator views without a 217k-row body materialization pass.

Full `daily-core` may still run periodic full backfill / parity audits until incremental drift checks are trusted.

---

## 10. Open questions

- Exact `feature_source_hash` algorithm and stability across Python versions.
- Whether `is_noise` requires body text at feature time (yes today) — noise rules cannot move before body read until noise heuristics are subject-only.
- Incremental invalidation when `document_master` changes without email row changes.
- Index strategy on `email_mart_features` (`direction`, `is_noise`, `sender_domain`) for rollup queries.
- Retention: whether deleted/archived emails remove feature rows or leave tombstones.

---

## What this doc does not do

- Does **not** implement schema, CLI, or builder changes
- Does **not** change `daily-core`, `build-mart`, or mart output tables
- Does **not** authorize Postgres mirror or dashboard schema changes

Implementation tracking starts with PR B after this doc merges.
