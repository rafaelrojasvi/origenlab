# Business mart (client-facing database layer)

Goal: provide **curated, searchable business entities** on top of the email archive without forcing the client to browse raw emails.

Raw archive remains unchanged:
- `emails`
- `attachments`
- `attachment_extracts`

Derived (rebuildable) layer:
- `contact_master`
- `organization_master`
- `document_master`
- `opportunity_signals`

Build script: `scripts/mart/build_business_mart.py`

## 1) Noise exclusions (conservative)
We exclude obvious system/non-business senders from the mart scan:
- `mailer-daemon`, `postmaster`
- delivery status / undeliverable subjects
- common NDR phrases (English/Spanish)

This logic is in `src/origenlab_email_pipeline/business_mart.py` (`is_noise_sender`).

## 2) Internal vs external
The mart focuses on **external contacts**.

Heuristic:
- internal domains are inferred from the most common sender domains (parsed from `emails.sender`)
- can be overridden by passing `--internal-domain yourdomain.com` (repeatable)

## 3) Organization name/type guesses
These are transparent heuristics:

- **organization_name_guess**:
  - derived from the second-level domain, normalized and title-cased
  - example: `soviquim.cl` → `Soviquim`

- **organization_type_guess**:
  - `education`: `.edu`, `.ac`, or common Chilean university domains/keywords
  - `government`: `.gov`, `gob.cl`
  - `consumer_email`: gmail/hotmail/outlook/yahoo/live
  - else `business`

## 4) Equipment tags
Equipment tags are keyword-based (same general intent as the report’s equipment section).

Tags:
- `microscopio`
- `centrifuga`
- `espectrofotometro`
- `phmetro`
- `autoclave`
- `balanza`
- `cromatografia_hplc`
- `incubadora`
- `titulador`
- `liofilizador`
- `horno_mufla`
- `pipetas`
- `humedad_granos`

Source text used for tagging:
- email `subject`
- `top_reply_clean` (fallback to `full_body_clean`)
- document preview (`attachment_extracts.text_preview`) for documents

## 5) Document master (`document_master`)
One row per extracted document (Phase 2.4), pulled from `attachment_extracts` where:
- `extract_status = 'success'`

Fields include:
- `doc_type` (rule-based from Phase 2.4)
- `extracted_preview_raw`: preview original/truncado
- `extracted_preview_clean`: preview limpiado para lectura
- `preview_quality_score` (0–1): heurístico de legibilidad
- boolean term signals (`has_*`)
- `equipment_tags` (comma-separated)

### Preview cleaning rules (Phase: UI-focused)
`extracted_preview_clean` intenta:
- colapsar whitespace y líneas vacías repetidas
- eliminar marcadores tipo `sep=,` (CSV)
- recortar líneas extremadamente largas (ruido de tablas XLSX/CSV/XML)
- truncar a un tamaño pequeño para lectura

No es “resumen inteligente”; es **limpieza conservadora**.

## 6) Contact master (`contact_master`)
One row per **external contact email**.

Direction:
- outbound email: sender domain is internal → external recipients are counted
- inbound email: sender domain is external → external sender is counted

Counts include:
- total/inbound/outbound interactions
- email-level intent flags (quote/invoice/purchase) from message text
- doc-level counts from `attachment_extracts` aggregated per email

## 7) Organization master (`organization_master`)
Rollup of `contact_master` grouped by domain.

Includes:
- total emails, contacts
- rollups of quote/invoice/purchase/doc metrics
- `key_contacts` = top 5 contact emails by volume (comma-separated)

## 8) Opportunity signals (`opportunity_signals`)
This is a small, explainable table of **heuristic “interesting” signals**.

Current MVP signals:
- `quote_email_plus_quote_doc`: contact has repeated quote-like emails and at least one quote doc
- `education_with_quote_activity`: education org with quote activity
- `dormant_contact`: historic contact (last seen before a cutoff) but high total volume
- `repeated_equipment_theme`: contact repeatedly mentions the same equipment tag

Each row includes:
- `signal_type`
- entity (`contact` / `organization`)
- `score` (0–1)
- `details_json` (why this was triggered)

## Rebuildability
Run with `--rebuild` to truncate and regenerate the mart tables deterministically from the archive + extracts.

## Streamlit UI (client-facing)
App: `apps/business_mart_app.py`

Estructura:
1. **Resumen** (KPIs + gráficos compactos)
2. **Contactos**
3. **Organizaciones**
4. **Documentos** (preview limpio + texto crudo en expander)
5. **Oportunidades** (señales con explicación en español)

