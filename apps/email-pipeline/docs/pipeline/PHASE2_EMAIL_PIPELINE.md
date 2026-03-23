# Phase 2 Email Pipeline (Unified)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-24

This document is the canonical implementation reference for Phase 2 body and attachment extraction.

## Scope

Phase 2 is split into four implemented layers:

1. Body extraction improvements (2.1)
2. Quote/signature cleaning (2.2)
3. Attachment metadata layer (2.3)
4. Selective attachment text extraction (2.4, no OCR)

---

## Phase 2.1 — Better body extraction

Goal: improve extracted text quality while keeping backwards compatibility.

Key additions:

- `extract_body_structured(msg)` in `parse_mbox.py`
- New email fields:
  - `body_text_raw`
  - `body_text_clean`
  - `body_source_type` (`plain|html|mixed|empty`)
  - `body_has_plain` / `body_has_html` (0/1)
- Ingestion (`02_mbox_to_sqlite.py`) populates both old and new fields.

Compatibility:

- Existing fields `body` and `body_html` remain intact.
- New analytics should prefer `body_text_clean`.

---

## Phase 2.2 — Quotes and signatures

Goal: produce two additional text variants for analysis:

- `full_body_clean` (best full text)
- `top_reply_clean` (newest reply with conservative quote/signature trimming)

Heuristics:

- Cuts on common reply headers (`On ... wrote:`, `El ... escribió:`, `-----Original Message-----`, etc.)
- Removes trailing signatures with conservative phrase matching (`Saludos`, `Atentamente`, `Best regards`, etc.)
- Falls back to `full_body_clean` when uncertain.

Operational path:

- Populated in ingestion.
- Backfill helper: `scripts/validation/backfill_phase2_2_text_fields.py`

---

## Phase 2.3 — Attachments metadata layer

Goal: add normalized attachment metadata without OCR/AI.

Schema additions:

- Email counters: `attachment_count`, `has_attachments`
- New `attachments` table with MIME metadata and hashes:
  - `email_id`, `part_index`, `filename`, `content_type`, `size_bytes`, `is_inline`, `sha256`, etc.

Detection logic:

- Preserve body parts as body.
- Record attachment/inline candidates conservatively from MIME headers/types.

Validation:

- `scripts/validation/validate_attachments.py`
- Focus on consistency between `emails` counters and `attachments` rows, plus orphan checks and type breakdown.

Report integration:

- Client report includes Phase 2.3 attachment summary metrics when table exists.

---

## Phase 2.4 — Selective attachment content extraction (no OCR)

Goal: extract lightweight text/structure from high-value non-inline business attachments.

New table:

- `attachment_extracts` linked to `attachments.id`
- Fields include `extract_status`, `extract_method`, truncated text, document-type signals.

Supported extraction:

- PDF text (PyMuPDF), DOCX, XLSX, CSV, XML
- Explicit statuses: `success|empty|skipped|failed|unsupported`

Run sequence:

```bash
cd apps/email-pipeline
uv run python scripts/validation/extract_attachment_text.py
uv run python scripts/validation/validate_phase2_4_extracts.py
uv run python scripts/reports/generate_client_report.py
```

Limitations:

- No OCR; image-only/scanned docs remain empty.
- Requires stable access to source mbox paths.

---

## Recommended usage

- For operations: use `RUNBOOK.md`.
- For architecture overview: use `ARCHITECTURE.md`.
- For deep per-phase history, old Phase-2 filenames remain as stubs to preserve links.
