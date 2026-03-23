# Phase 2.1 — Post-ingestion validation

**Date:** After full ingestion (590,606 rows).  
**DB:** `/home/rafael/data/origenlab-email/sqlite/emails.sqlite`

---

## 1. New Phase 2.1 fields verified

All five new columns exist and are populated by the ingestion script:

| Column             | Type    | Purpose |
|--------------------|--------|---------|
| `body_text_raw`    | TEXT   | Primary extracted text (plain preferred; legacy HTML→text when no plain). |
| `body_text_clean`  | TEXT   | Best readable text (normalized plain or improved HTML cleaning). |
| `body_source_type` | TEXT   | `plain` \| `html` \| `mixed` \| `empty`. |
| `body_has_plain`   | INTEGER| 1 if any text/plain part present, else 0. |
| `body_has_html`    | INTEGER| 1 if any text/html part present, else 0. |

Schema was applied additively via `init_schema()` (ALTER TABLE); no migration script required.

---

## 2. Validation summary (from DB inspection)

### Total row count

- **590,606** rows (after full 2.1 ingestion).

### Counts by `body_source_type`

Run the validation script for the full breakdown:

```bash
uv run python scripts/validation/validate_phase2_1.py
```

**Note:** On ~590k rows, the first run can take 3–5 minutes (full table scans for GROUP BY and non-empty counts). The script creates `idx_emails_body_source_type` to speed up later runs. Expected output includes:

- Counts per `body_source_type`: `plain`, `html`, `mixed`, `empty` (and any NULL/other).
- Non-empty `body_text_raw` vs non-empty `body_text_clean` (should be very close; clean may slightly exceed raw when HTML cleaning improves content).
- Counts by `(body_has_plain, body_has_html)`.
- Two sample rows each for `plain`, `html`, and `mixed` (id, length, first 100 chars of `body_text_clean`).

### Non-empty raw vs clean body counts

From the validation run:

- **body_text_raw non-empty:** 555,749  
- **body_text_clean non-empty:** 555,749

Given 590,606 total rows and 33,749 rows with `body_source_type = 'empty'`, we expect:

- Rows with `body_source_type != 'empty'`: 590,606 − 33,749 = **556,857**  
- Difference vs non-empty clean bodies: 556,857 − 555,749 ≈ **1,108** rows.

These ~1,108 rows are the focus of the 2.1.1 anomaly check below.

### has_plain / has_html counts

From the validation run:

- `has_plain=0, has_html=1` (html-only): 249,842  
- `has_plain=1, has_html=1` (mixed): 173,842  
- `has_plain=1, has_html=0` (plain-only): 133,173  
- `has_plain=0, has_html=0` (no text/plain and no text/html): 33,749

### Sample examples (plain / html / mixed)

- The validation script prints two sample rows per source type with `id`, length of `body_text_clean`, and a short substring. In the run on the full dataset:
  - `plain` samples are normal Spanish business emails (greetings, invoices, orders).
  - `mixed` samples include DHL / billing-style messages with long, structured content.
  - `html` samples for the anomalous case (see below) have non-empty `body_html` but zero-length `body_text_raw` and `body_text_clean` (likely image-only or layout-only HTML).

### Obvious anomalies checked (2.1.1)

- **Rows with `body_source_type = 'empty'` but non-empty `body_text_raw`:** Count is 0 (as expected; `empty` means no text/plain and no text/html parts were found).
- **Rows with `body_source_type != 'empty'` but blank `body_text_clean`:**
  - Implied count: ~1,108 rows (difference between `source_type != 'empty'` total and non-empty `body_text_clean`).
  - Sampled rows (20+) show:
    - `body_source_type = 'html'`.
    - `LENGTH(body) = 0`, `LENGTH(body_html) > 0`.
    - `LENGTH(body_text_raw) = 0`, `LENGTH(body_text_clean) = 0`.
  - Likely cause: HTML parts that contain no real text (e.g. tracking pixels, empty templates, image-only content) so `html_to_text_improved` legitimately produces an empty string.

**Decision:**  
- This behaviour is acceptable for Phase 2: these messages truly have no meaningful text content for analytics.  
- We **do not** reclassify them to `body_source_type = 'empty'` to avoid an extra pass over the table; instead we document the anomaly and treat them as “html with no visible text”.  
- Downstream analytics should primarily use `body_text_clean` and can treat `body_text_clean = ''` as “no usable body text”, regardless of `body_source_type`.

---

## 3. Message-ID dedupe summary

From direct SQL on the loaded DB (no dedupe script run yet):

| Metric | Value |
|--------|--------|
| **Raw rows** | 590,606 |
| **Rows with missing/empty Message-ID** | 22,555 |
| **Unique keys** (one per distinct Message-ID, or per row when Message-ID is null/empty) | 230,907 |
| **Duplicate rows** (would be removed by dedupe) | 359,699 |
| **Duplicate rate** | **~60.9%** |

Interpretation:

- Many rows share the same `Message-ID` (e.g. same message in multiple PST/mbox sources). The dedupe script `scripts/tools/dedupe_emails_by_message_id.py` keeps one row per `Message-ID` (or per `id` when `Message-ID` is null).
- After running dedupe, expected row count is **~230,907** (plus any rows with null/empty Message-ID, which are each kept as separate rows).

### How to run dedupe

```bash
uv run python scripts/tools/dedupe_emails_by_message_id.py
```

Output format: `Before: 590,606 rows | After: 230,907 rows | Removed: 359,699 duplicates` (numbers may vary slightly if DB changed).

---

## 4. Validation script

- **Script:** `scripts/validation/validate_phase2_1.py`
- **Usage:** `uv run python scripts/validation/validate_phase2_1.py`
- **Requires:** `.env` (or env) so `load_settings().resolved_sqlite_path()` points to the DB.
- **Side effect:** Creates `CREATE INDEX IF NOT EXISTS idx_emails_body_source_type ON emails(body_source_type)` to speed up aggregation.

---

## 5. Conclusion

- Phase 2.1 fields are present and populated by the current ingestion.
- Message-ID dedupe is still the authoritative step; current load has a high duplicate rate (~61%); run dedupe when you want a unique-message view.
- For a full validation breakdown (counts by source type, has_plain/has_html, samples), run `validate_phase2_1.py` once (allow a few minutes on 590k rows).

---

## 6. Next: Phase 2.2 implementation plan (proposed, not implemented)

After validation, Phase 2.2 can proceed as follows.

### Goal

- Store **full_body_clean** and **top_reply_clean** so analytics can use “top reply” text (without quoted chains and signatures) while keeping the full cleaned body.

### Schema changes

- Add to `emails` (additive):
  - `full_body_clean` TEXT — full cleaned body (e.g. copy of `body_text_clean` or normalized from `body`).
  - `top_reply_clean` TEXT — same body with quoted reply blocks and signature blocks stripped (heuristic).

### Parser / logic

- New module or functions in `parse_mbox` (or `src/.../quotes_signatures.py`):
  - **Reply detection:** Patterns for “On … wrote:”, “El … escribió:”, “From: … Sent: …”, “>” quote lines; configurable list.
  - **Signature detection:** Separators like `-- `, `__`, “Enviado desde …”; configurable.
  - **`extract_quote_signature(body_clean: str) -> dict`** returning:
    - `full_body_clean`: normalized full text (e.g. strip trailing whitespace, consistent newlines).
    - `top_reply_clean`: text before first reply block and before signature.

- Do **not** overwrite `body`, `body_text_raw`, or `body_text_clean`; only write the two new columns.

### Ingestion

- In `02_mbox_to_sqlite.py`, after `extract_body_structured(msg)`:
  - Set `full_body_clean = structured["body_text_clean"]` (or `body` if no clean).
  - Compute `top_reply_clean` via `extract_quote_signature(full_body_clean)`.
  - Pass both into `insert_email()`.

### Tests

- Plain message (no quotes/signatures) → `top_reply_clean` ≈ `full_body_clean`.
- English reply header (“On … wrote:”) → reply block not in `top_reply_clean`.
- Spanish reply header (“El … escribió:”) → same.
- Signature separator (`-- `, etc.) → signature not in `top_reply_clean`.
- Message with no quoted content → both outputs identical.

### Doc

- Add **`docs/PHASE2_QUOTES_SIGNATURES.md`** (heuristics, config, field semantics).

### Implementation order

1. Implement `extract_quote_signature()` and tests.
2. Add schema columns and `insert_email()` params.
3. Wire ingestion to new fields.
4. Write PHASE2_QUOTES_SIGNATURES.md.

Do **not** implement 2.2 until you are satisfied with 2.1 validation and dedupe.
