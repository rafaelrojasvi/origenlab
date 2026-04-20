# PostgreSQL Archive Data Migration Plan V1

## 1. Purpose

This document describes a **future, one-way data copy** from the operational **SQLite** archive tables (`emails`, `attachments`, `attachment_extracts`) into the **PostgreSQL** `archive` schema tables created by Alembic revision `20260419_0002` (`archive.emails`, `archive.attachments`, `archive.attachment_extracts`).

- **SQLite remains the runtime source of truth** for ingestion and existing tooling until a project-wide cutover is explicitly decided.
- **No application code changes** are implied by this plan; it is a design for a standalone migration job (batch script) and its validation.
- **Out of scope for this plan:** migrating `document_master` or any `mart.*` tables; those depend on stable archive identifiers and are addressed after archive backfill (see §10).

Reference DDL: `POSTGRES_SCHEMA_RECONCILIATION_V1.md` §6.1, Alembic `20260419_0002_archive_emails_attachments_extracts.py`.

---

## 2. Preconditions

| Requirement | Notes |
|-------------|--------|
| **Alembic** | Target database upgraded to at least **`20260419_0002`** (schemas + ops + archive tables). |
| **SQLite validator** | Read-only validator (`scripts/qa/validate_sqlite_archive_for_postgres.py`) passes **`--strict`** (no invalid timestamps/booleans, no orphan FKs, no empty `source_file`). |
| **Source path** | **`ORIGENLAB_SQLITE_PATH`** (or explicit CLI) points at the canonical SQLite file to copy. |
| **Target URL** | **`ORIGENLAB_POSTGRES_URL`** or **`ALEMBIC_DATABASE_URL`** (or explicit CLI) points at the target Postgres instance and database. |
| **Target data state** | Archive tables are **empty**, or the operator runs in an explicit **`--replace`** mode (see §5). Default behavior must refuse to overwrite non-empty targets. |
| **Capacity / time** | Order-of-magnitude source size (validated corpus): **~216k** emails, **~449k** attachments, **~14k** extracts; plan for long-running batch job and sufficient Postgres disk. |

`document_master` exists only in SQLite for mart use; it is **not** part of this archive migration slice.

---

## 3. Source-to-target mapping

### 3.1 `emails` → `archive.emails`

| SQLite `emails` | Postgres `archive.emails` | Conversion |
|-----------------|----------------------------|------------|
| `id` | `id` | `INTEGER` → `BIGINT`; preserve value (see §4). |
| `source_file` | `source_file` | `TEXT` → `TEXT` (NOT NULL). |
| `folder` | `folder` | `TEXT` → `TEXT`. |
| `message_id` | `message_id` | `TEXT` → `TEXT` (indexed, **not unique**). |
| `subject` | `subject` | `TEXT` → `TEXT`. |
| `sender` | `sender` | `TEXT` → `TEXT`. |
| `recipients` | `recipients` | `TEXT` → `TEXT`. |
| `date_raw` | `date_raw` | `TEXT` → `TEXT`. |
| `date_iso` | `date_iso` | `TEXT` → **`TIMESTAMPTZ`** (see below). |
| `body` | `body` | `TEXT` → `TEXT`. |
| `body_html` | `body_html` | `TEXT` → `TEXT`. |
| `body_text_raw` | `body_text_raw` | `TEXT` → `TEXT`. |
| `body_text_clean` | `body_text_clean` | `TEXT` → `TEXT`. |
| `body_source_type` | `body_source_type` | `TEXT` → `TEXT`. |
| `body_has_plain` | `body_has_plain` | `INTEGER` (0/1/NULL) → **`BOOLEAN`**. |
| `body_has_html` | `body_has_html` | same |
| `full_body_clean` | `full_body_clean` | `TEXT` → `TEXT`. |
| `top_reply_clean` | `top_reply_clean` | `TEXT` → `TEXT`. |
| `attachment_count` | `attachment_count` | `INTEGER` → `INTEGER`. |
| `has_attachments` | `has_attachments` | `INTEGER` (0/1/NULL) → **`BOOLEAN`**. |

**Timestamp conversion (`date_iso`):** Use the same rules as the validator: normalize trailing `Z` / `z` to `+00:00`, then parse to a timezone-aware value and bind as `TIMESTAMPTZ`. `NULL` stays `NULL`. Any value that would fail strict validation must **abort** the run with a row-identified error (§7).

### 3.2 `attachments` → `archive.attachments`

| SQLite `attachments` | Postgres `archive.attachments` | Conversion |
|----------------------|---------------------------------|------------|
| `id` | `id` | Preserve (see §4). |
| `email_id` | `email_id` | Preserve; must reference loaded `archive.emails.id`. |
| `part_index` | `part_index` | `INTEGER` → `INTEGER`. |
| `filename` | `filename` | `TEXT` → `TEXT`. |
| `content_type` | `content_type` | `TEXT` → `TEXT`. |
| `content_disposition` | `content_disposition` | `TEXT` → `TEXT`. |
| `size_bytes` | `size_bytes` | `INTEGER` → **`BIGINT`**. |
| `content_id` | `content_id` | `TEXT` → `TEXT`. |
| `is_inline` | `is_inline` | `INTEGER` (0/1/NULL) → **`BOOLEAN`**. |
| `sha256` | `sha256` | `TEXT` → `TEXT`. |
| `saved_path` | `saved_path` | `TEXT` → `TEXT`. |
| `created_at` | `created_at` | `TEXT` → **`TIMESTAMPTZ`** (same parsing rules as `date_iso`). |

### 3.3 `attachment_extracts` → `archive.attachment_extracts`

| SQLite `attachment_extracts` | Postgres `archive.attachment_extracts` | Conversion |
|------------------------------|------------------------------------------|------------|
| `id` | `id` | Preserve (see §4). |
| `attachment_id` | `attachment_id` | Preserve; must reference loaded `archive.attachments.id`; **unique** in Postgres. |
| `extract_status` | `extract_status` | `TEXT` → `TEXT` (NOT NULL). |
| `extract_method` | `extract_method` | `TEXT` → `TEXT` (NOT NULL). |
| `text_preview` | `text_preview` | `TEXT` → `TEXT`. |
| `text_truncated` | `text_truncated` | `TEXT` → `TEXT`. |
| `char_count` | `char_count` | `INTEGER` → `INTEGER`. |
| `page_count` | `page_count` | `INTEGER` → `INTEGER`. |
| `sheet_count` | `sheet_count` | `INTEGER` → `INTEGER`. |
| `detected_doc_type` | `detected_doc_type` | `TEXT` → `TEXT`. |
| `has_quote_terms` | `has_quote_terms` | `INTEGER` (0/1/NULL) → **`BOOLEAN`**. |
| `has_invoice_terms` | `has_invoice_terms` | same |
| `has_price_list_terms` | `has_price_list_terms` | same |
| `has_purchase_terms` | `has_purchase_terms` | same |
| `error_message` | `error_message` | `TEXT` → `TEXT`. |
| `created_at` | `created_at` | `TEXT` → **`TIMESTAMPTZ`**. |

### 3.4 Type conversions (summary)

| Source | Target | Rule |
|--------|--------|------|
| ISO-like `TEXT` | `TIMESTAMPTZ` | Parse with validator-equivalent logic; `NULL` unchanged. |
| `INTEGER` 0 / 1 / `NULL` | `BOOLEAN` | `0` → false, `1` → true, `NULL` → `NULL`. Any other integer → **abort**. |
| Plain integers / IDs | `BIGINT` | Safe widening; preserve numeric identity. |

---

## 4. ID preservation strategy

**Recommendation: preserve SQLite surrogate keys** for `emails.id`, `attachments.id`, and `attachment_extracts.id` when inserting into Postgres.

**Reasoning:**

- Child relationships (`attachments.email_id`, `attachment_extracts.attachment_id`) are already consistent in SQLite; copying the same integers avoids remapping and keeps human debugging and logs aligned across systems.
- Future work (e.g. **`mart.document_master`**, which keys on `attachment_id` and references `email_id`) is simpler if archive IDs in Postgres match SQLite **1:1**.
- Postgres sequences (`emails_id_seq`, etc.) must be advanced after load so the next auto-generated ID does not collide.

**Mechanism (future implementation):**

1. Insert rows with **explicit `id`** columns (batch `INSERT ...` with column lists including `id`).
2. After successful commit of each table (or once at end), run **`setval`** on each sequence to `MAX(id)` (or `MAX(id)` + 1 per Postgres convention for `setval` with `is_called`).

**Collision check:** If the target already contains conflicting IDs, the job must fail unless **`--replace`** has cleared tables in FK-safe order (§5).

---

## 5. Load strategy

**Order:** Always load **`archive.emails` first**, then **`archive.attachments`**, then **`archive.attachment_extracts`**, respecting foreign keys.

**Batching:**

- Read from SQLite in **keyset or chunked ranges** (e.g. `WHERE id > ? ORDER BY id LIMIT ?`) to avoid loading millions of rows into memory.
- Write to Postgres with **multi-row inserts** (`executemany` or bulk `COPY` / `execute_values`) sized by **`--batch-size`** (e.g. 1k–10k rows per batch; tuned in implementation).

**Transactions:**

- Prefer **one transaction per batch** or **one transaction per table** (trade-off: rollback granularity vs WAL size). Minimum: emails committed before attachments start; attachments before extracts.
- Avoid a single transaction for the full 400k+ attachment load unless Postgres memory and WAL limits are verified.

**Default vs replace:**

| Mode | Behavior |
|------|----------|
| **Default** | If **any** target archive table is non-empty, **exit with error** (no truncate, no delete). |
| **`--replace`** | Requires explicit flag. **Truncate** in FK-safe order: `archive.attachment_extracts` → `archive.attachments` → `archive.emails` (or `DELETE` in same order if truncate not preferred for FK reasons). Then run full load. Document that this is destructive on the **Postgres archive slice only**. |

**No partial destructive behavior by default:** No “upsert only half the emails” or silent skip of bad rows without abort.

---

## 6. Validation after load

Run automated checks **before** declaring success. Suggested queries (conceptual):

| Check | Description |
|-------|-------------|
| **Row counts** | `COUNT(*)` per table matches SQLite for `emails`, `attachments`, `attachment_extracts`. |
| **ID ranges** | `MIN(id)`, `MAX(id)` match between SQLite and Postgres per table. |
| **FK coverage** | Zero orphans: `attachments.email_id` ⊆ `emails.id`; `attachment_extracts.attachment_id` ⊆ `attachments.id` (should match validator + load order). |
| **Timestamps** | Count of non-null `date_iso` / `created_at` columns matches SQLite; spot-check parseability (already guaranteed if conversion reused). |
| **Booleans** | Distribution of NULL / true / false per column matches expectations (compare counts from SQLite vs Postgres after mapping). |
| **Duplicates** | Count of duplicate **non-null** `message_id` groups / extra rows matches SQLite (validator-style duplicate metrics). |
| **Gmail Sent** | Count of rows with `source_file LIKE 'gmail:%'` and `folder IN ('[Gmail]/Enviados','[Gmail]/Sent Mail')` matches SQLite (example validated corpus: **350**). |
| **Checksum / hash** | Optional: compute a stable hash over concatenated selected columns (e.g. `id`, `date_iso`, `sha256`) per table or per batch to detect silent corruption. |

If any check fails, exit non-zero and write details to **`--json-out`** (§8).

---

## 7. Failure behavior

| Situation | Behavior |
|-----------|----------|
| Target archive tables non-empty | **Fail** immediately unless **`--replace`**. |
| **`--replace`** | Only allowed as an **explicit** CLI flag; log and document truncation. |
| Invalid timestamp or boolean at conversion | **Abort** the batch (or whole job); do not insert partial batch without a defined strategy (default: abort). |
| Errors | Every error should identify **table**, **source row id** (SQLite PK), and **column** where applicable. |
| Postgres errors | Surface SQLSTATE / constraint name when relevant (unique violation on `attachment_id`, etc.). |

---

## 8. Future script sketch

Planned location: **`scripts/migrate/sqlite_archive_to_postgres.py`** (not implemented in this document).

**Responsibilities:**

- Open SQLite read-only; connect to Postgres with a migration-appropriate URL.
- Enforce preconditions (validator exit or re-run checks).
- Load in order (§5), preserve IDs (§4), reset sequences.
- Run post-load validation (§6).
- Emit human-readable progress and structured **`--json-out`** summary.

**CLI (sketch):**

| Option | Purpose |
|--------|---------|
| `--sqlite-db` | Path to SQLite file (overrides env if set). |
| `--postgres-url` | Connection URL (overrides `ORIGENLAB_POSTGRES_URL` / `ALEMBIC_DATABASE_URL`). |
| `--batch-size` | Rows per batch (default TBD). |
| `--replace` | Truncate archive tables in FK-safe order, then load. |
| `--dry-run` | Validate mapping and counts without committing inserts (or use a transaction rolled back). |
| `--json-out` | Path to write machine-readable report (counts, timings, validation results). |

---

## 9. Tests for future implementation

When the script exists, automated tests should cover:

1. **Clean small DB:** Synthetic SQLite with a few emails / attachments / extracts migrates; Postgres counts and IDs match.
2. **Non-empty target:** Second run without `--replace` **fails** fast.
3. **`--replace`:** Truncates in **FK-safe order** and allows a full reload.
4. **ID preservation + sequences:** Explicit IDs match SQLite; `setval` verified (next insert gets non-colliding id).
5. **Invalid timestamp:** Injected bad `date_iso` causes **abort** with identifiable row.
6. **Invalid boolean:** Injected non-0/1 integer causes **abort**.
7. **Validation mismatch:** Forced count skew detected; job **fails** post-load validation.

Tests should **not require real Postgres** for unit-level logic where possible (use mocks or docker optional integration job).

---

## 10. Recommendation

**Implement the archive data migration script (`sqlite_archive_to_postgres.py`) before adding `mart.document_master` (or other mart tables) in Postgres.**

**Because:** `document_master` (and related marts) logically depend on **stable `email_id` and `attachment_id`** values tied to the archive. Loading the archive first with preserved IDs establishes the spine for a later mart migration or rebuild against Postgres.

---

## Appendix: Reference scale (validated corpus)

These numbers are **examples** from a strict-passing snapshot; actual counts must be re-read at migration time.

| Table | Approx. rows |
|-------|----------------|
| `emails` | 216,352 |
| `attachments` | 449,462 |
| `attachment_extracts` | 14,061 |
| `document_master` (SQLite only; not migrated here) | 12,266 |

---

## Open questions

1. **`COPY` vs parameterized `INSERT`:** For maximum throughput, `COPY FROM STDIN` may beat batched inserts; requires format alignment and error handling. Decide in implementation based on benchmarks.
2. **Parallelism:** Whether to parallelize attachment batches by `email_id` ranges (must not violate FK visibility within transactions).
3. **Networked SQLite:** If the SQLite file is on slow storage, whether to copy locally before migration.
4. **Cutover:** When to switch application reads to Postgres is a separate product decision; this plan only covers **backfill**.

---

## Main decisions (summary)

| Topic | Decision |
|-------|----------|
| Scope | SQLite `emails`, `attachments`, `attachment_extracts` → Postgres `archive.*` only. |
| IDs | **Preserve** SQLite IDs; **reset sequences** after load. |
| Types | ISO `TEXT` → **`TIMESTAMPTZ`**; 0/1/NULL → **`BOOLEAN`**; `size_bytes` → **`BIGINT`**. |
| Safety | Default **fail if target non-empty**; **`--replace`** explicit; **no silent partial loads**. |
| Order | **Emails → attachments → extracts**; validation after commit. |
| Next step | **Archive migration script before** `mart.document_master` DDL/migration in Postgres. |
