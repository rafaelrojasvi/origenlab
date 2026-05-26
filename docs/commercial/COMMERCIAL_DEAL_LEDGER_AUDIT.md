# Commercial deal ledger — schema audit (2026-05-26)

Read-only audit for a durable **buy / sell / margin** layer. Prototype deal: **SERVA → CEAF** (OC 26172, PO 174-26).

## Step 1 — Existing tables

### SQLite (operational archive + mart)

| Table | Role | Enough for buy/sell/margin ledger? |
|-------|------|-------------------------------------|
| `emails`, `attachments`, `attachment_extracts` | Raw archive + PDF text previews | Evidence only |
| `document_master` | Mart: doc_type, sender/recipient domain, preview text, quote/invoice flags | Per-attachment signals; no deal rollup |
| `commercial_purchase_events` | **Buyer-side** confirmed PO (CEAF preset) | **Partial** — client purchase only; no supplier cost, FX, margin |
| `commercial_purchase_event_items` | Line items on buyer event | Client lines only |
| `commercial_purchase_event_attachments` | Linked filenames | Evidence |
| `commercial_email_signal_fact` | Rebuildable email signals | Org/contact intel, not deals |
| `commercial_org_signal_rollup`, `commercial_contact_signal_rollup` | Rollups | Not deals |
| `commercial_opportunity_fact` | Org-level opportunity keys | Prospecting, not executed deals |
| `organization_candidate`, `contact_candidate`, `opportunity_candidate` | Human review queue | Not ledger |
| `contact_master`, `organization_master`, `opportunity_signals` | Business mart | Not commercial ledger |

**`commercial_purchase_events` columns (buyer-centric):**  
`source_email_id`, `buyer_org_name`, `buyer_contact_email`, `buyer_domain`, `purchase_status`, `oc_number`, `oc_date`, `quote_number`, `net_amount_clp`, `iva_amount_clp`, `gross_amount_clp`, `currency` (default CLP), `payment_terms`, `commercial_summary`, `confidence`, `evidence_json`, …

**Gap:** No `supplier_org`, `supplier_po_number`, `supplier_cost`, `supplier_currency`, `client_invoice_number`, `supplier_invoice_number`, payment vouchers, logistics state, or `gross_margin_*`.

### Postgres (read mirror — dashboard)

| Schema.table | Source | Notes |
|--------------|--------|-------|
| `commercial.purchase_event` | SQLite `commercial_purchase_*` sync | Same buyer-only model |
| `commercial.purchase_event_item` | Items sync | |
| `commercial.purchase_event_attachment` | Attachments sync | |
| `commercial.warm_case` (+ linked_email, status_history, event) | Warm operator queue | **Not** a ledger; no margin |
| `commercial.equipment_opportunity` | Tender/equipment signals | Separate domain |
| `archive.emails`, `archive.attachments`, `archive.attachment_extracts` | Archive mirror | No bodies on Render policy |
| `mart.document_master` | Mart mirror | |

**No** `commercial.deal` or supplier-side purchase tables in Postgres today.

### Code / operator paths

- **Promotion:** `scripts/commercial/promote_purchase_order_event.py` — CEAF OC 26172 → SQLite `commercial_purchase_events` (`--apply` writes SQLite only).
- **Warm cases:** Postgres `commercial.warm_case` — operator queue; SERVA/CEAF threads classified in `warm_case_sender_rules.py`.
- **Dashboard API:** `GET /mirror/commercial/purchase-events` — buyer events only.

### Verdict on `commercial_purchase_events`

Treat as **event-level buyer confirmation**, not a full **deal ledger**. Safe approach: **keep** for promoted buyer POs; add **`commercial_deal*`** tables as durable rollup (do not overload purchase_events with nullable supplier columns).

---

## Step 2 — Recommended schema (SQLite first)

**Canonical design (v1.1):** [`COMMERCIAL_DEAL_LEDGER_SCHEMA_V1.md`](COMMERCIAL_DEAL_LEDGER_SCHEMA_V1.md) — full ERD, enums, table DDL (incl. `commercial_deal_field_evidence`, `amount_minor`, reproducibility metadata), SERVA/CEAF mapping, **§13 Phase 1 implementation plan**. **No migrations applied yet.**

Summary (superseded in detail by v1 doc):

New tables (namespaced; migrations after preview sign-off):

### `commercial_deal`

Deal rollup: client + supplier + PO/invoice numbers + amounts + margin fields + `status` + `confidence` + `notes_json`.

Suggested `deal_key`: `serva-ceaf-oc-26172-po-174-26` (unique).

### `commercial_deal_line`

SKU-level sale/cost lines per deal.

### `commercial_deal_event`

Timeline: `client_po_received`, `supplier_po_sent`, `supplier_payment_sent`, `logistics_pending`, etc. Links `email_id` / `attachment_id` without storing full bodies.

### `commercial_deal_document`

Typed documents: `client_po`, `supplier_invoice`, `payment_voucher`, … + `doc_number`, `amount`, `currency`, extract status.

**Postgres:** Mirror under `commercial.deal*` only after SQLite stable and **Cloudflare Access** on dashboard. No full email bodies on Render.

---

## Step 3 — Prototype (implemented)

Read-only script:

```bash
cd apps/email-pipeline
uv run python scripts/commercial/extract_serva_ceaf_deal_preview.py
```

Outputs:

- `serva-ceaf-oc-26172-po-174-26.json` — operator preview (full transfer/operation IDs for local review)
- `serva-ceaf-oc-26172-po-174-26.public.json` — redacted (safe if dashboard/API ever exposes deal cards)
- `serva-ceaf-oc-26172-po-174-26.csv` — flat summary

**Operator-confirmed SERVA/CEAF facts (2026-05-26):** `serva_ceaf_deal_confirmed.py` — client payment CLP 1,499,400; SERVA proforma EUR 363 (products 148 + handling 70 + freight 145); Wise EUR 218 reconciled as proforma minus freight; `deal_status=paid_by_client__supplier_payment_sent__logistics_pending`.

---

## Step 4 — Ingestion plan (after preview verified)

1. Operator reviews JSON `missing_fields` and `confidence` per field.
2. SQLite migration: `commercial_deal*` DDL + optional seed from preview (explicit `--apply` only).
3. Optional promotion helper: link existing `commercial_purchase_events` row for OC 26172 → `commercial_deal.id`.
4. Postgres Alembic + `sync_*` mirror — **explicit approval**; no bodies.
5. API/dashboard cards — **after Access/auth**; read-only GET.

---

## Safety (first pass)

| Check | Status |
|-------|--------|
| Gmail mutation | **No** |
| Email send | **No** |
| Outreach / warm_case writes | **No** |
| SQLite writes | **No** (read-only URI) |
| Postgres writes | **No** |
| Mart rebuild | **No** |
| Render deploy | **No** |
