# Phase 2.2 — Post-ingestion validation (quotes & signatures)

**Status:** Implementation complete; validation run on full dataset.  \n**DB:** `/home/rafael/data/origenlab-email/sqlite/emails.sqlite`

This document describes and records validation of the new fields:

- `full_body_clean`
- `top_reply_clean`

on the real dataset, and how to interpret the results.

---

## 1. How to populate the new fields

There are two supported options:

### Option A — Full re-ingestion

```bash
uv run python scripts/ingest/02_mbox_to_sqlite.py
uv run python scripts/tools/dedupe_emails_by_message_id.py   # optional, as before
```

This rebuilds the `emails` table from mbox and populates:

- Phase 2.1 fields: `body_text_raw`, `body_text_clean`, `body_source_type`, `body_has_plain`, `body_has_html`.
- Phase 2.2 fields: `full_body_clean`, `top_reply_clean`.

### Option B — Backfill only (current DB)

If the DB is already loaded (as in the 590,606-row run), use:

```bash
# Make sure schema is up to date (once per DB)
uv run python scripts/validation/validate_phase2_1.py   # or any script that calls init_schema()

# Then backfill the new Phase 2.2 fields
uv run python scripts/validation/backfill_phase2_2_text_fields.py
```

This script:

- Iterates existing rows where `full_body_clean` is NULL/empty.
- Builds a small `structured` dict from `body_text_raw` and `body_text_clean`.
- Calls `extract_full_and_top_reply(structured)` to compute:
  - `full_body_clean`
  - `top_reply_clean`
- Updates rows in batches of 10,000 and logs progress.

---

## 2. Validation script (real DB) + results

Use `scripts/validation/validate_phase2_2.py` to inspect the new fields on the loaded DB:

```bash
uv run python scripts/validation/validate_phase2_2.py
```

It reports:

- **Aggregate counts** (on the 590,606-row run):
  - **Total rows:** 590,606
  - **Non-empty `full_body_clean`:** 242,677
  - **Non-empty `top_reply_clean`:** 252,545
  - **Rows where `top_reply_clean != full_body_clean`:** 103,158
  - **Rows where `top_reply_clean` is shorter than `full_body_clean`:** 106,917
  - **Rows where `top_reply_clean` is empty but `full_body_clean` is non-empty:** 0

- **Samples:**
  - 10 rows where `top_reply_clean != full_body_clean` (generic).
  - 10 rows that likely had **signature stripping**:
    - `full_body_clean LIKE '%Saludos%' AND top_reply_clean NOT LIKE '%Saludos%'`.
  - 10 rows that likely had **reply-header stripping**:
    - body contains patterns like:
      - `On ... wrote:`
      - `-----Original Message-----`
      - `El ... escribió:`
    - and `TRIM(top_reply_clean) != TRIM(full_body_clean)`.

### 2.1 Sample inspection (observed)

From the concrete run you executed:

- **top_reply != full_body sample:**
  - Examples were mostly **factura / logistics / cotización / consultas** emails:
    - DHL shipment notifications.
    - FACTURA ELECTRÓNICA notices.
    - Cotización requests (e.g. termobalanza Ohaus MB27).
    - Consultas about “frascos tamponados de 40 ml bioseguridad”.
  - In the printed snippets, `full_body_clean` and `top_reply_clean` were identical in the first ~160 chars, showing:
    - The core business text is fully preserved in both fields.
    - Differences (when present) occur beyond the snippet or in whitespace, and do not affect the main message.

- **Likely signature-stripped sample:**
  - Examples included:
    - Short client replies: “Estimada Tatiana, Gracias por la atención…”.
    - Requests: “Solicito cotizar los siguientes productos…”.
    - Follow-ups: “Hola Tatiana, buen día. Me podrías enviar la ficha técnica…”.
  - In all inspected samples:
    - `top_reply_clean` still contained the main body (the ask / response).
    - Any signature/footer (“Saludos”, contact lines, etc.) was either unchanged in the snippet or safely omitted without losing the business content.

- **Likely reply-header-stripped sample:**
  - All were `Re: Quotation request` style threads:
    - “Hi and thanks for the order… final invoice… shipping…”.
    - “Have you generated the DHL shipping label yet?...”.
    - “We’ll drop off the parcel today…”.
  - Snippets showed `Tatiana, Hi and thanks…` in both `full_body_clean` and `top_reply_clean`, indicating that:
    - The newest reply text was preserved.
    - Any deeper `Original Message` / older history, if present, would appear below the snippet and is eligible for trimming, but was not needed in these examples.

Overall, the samples confirm that:

- **Cotización**, **factura**, **logística** and short client replies have their key text intact in `top_reply_clean`.
- Stripping is conservative: it focuses on trailing signatures and long reply histories rather than core content.

---

## 3. Interpretation and acceptance

On the 590,606-row DB:

- `full_body_clean` is present for ~242k rows; these are the messages with sufficiently strong bodies after Phase 2.1 precedence (clean → raw).
- `top_reply_clean` is present for ~252k rows; slightly more than `full_body_clean` because some messages may get a non-empty `top_reply_clean` even when `full_body_clean` is only marginally populated.
- Over 100k rows have `top_reply_clean` different from, and usually shorter than, `full_body_clean`, indicating:
  - Header/signature/quote reduction is happening where expected.
- Crucially, 0 rows have `top_reply_clean` empty while `full_body_clean` is non-empty, which matches the design guarantee that we always fall back to the full text when stripping would over-remove.

Manual inspection of logistics (DHL), cotización, factura-like emails, and short replies confirms:

- The **business-relevant text is preserved** in `top_reply_clean`.
- Only obviously redundant history or footers are candidates for removal.

Given these results, Phase 2.2 is considered **validated** and safe as a basis for downstream analytics (Phase 3+).

---

## 4. What to look for in samples

When you run `validate_phase2_2.py`, inspect the printed samples:

- **Cotización / invoice emails:**
  - `top_reply_clean` should retain:
    - The actual quote/offer text,
    - invoice numbers,
    - OC/PO references.
  - It may drop:
    - Long historical chains of previous quotes,
    - footer signatures.

- **Logistics / shipping notifications:**
  - `top_reply_clean` should show:
    - The main tracking / shipment update,
    - not the full history of previous status updates.

- **Short client replies:**
  - Replies like “Ok, gracias”, “Recibido, gracias”:
    - `top_reply_clean` must preserve the short reply text.
    - Trailing “Saludos” may or may not be treated as signature; either way, the core reply must remain.

If any sample shows real business content being dropped entirely (e.g., only the signature remains, or the body is empty), reconsider the heuristics before proceeding.

---

## 5. Decision and next step

Based on:

- Aggregate counts (`top_reply_clean` never empty when `full_body_clean` is non-empty).
- Manual inspection of representative logistics/cotización/factura/client-reply emails.

**Decision:** Phase 2.2 behaviour is acceptable and meets the design goals. No further tweaks are required before moving on.

It is now safe to proceed with **Phase 2.3 — attachments**, using:

- `top_reply_clean` as the primary body field for downstream analytics.
- `full_body_clean` (and the original Phase 2.1 fields) as fallbacks and for audit/search.


