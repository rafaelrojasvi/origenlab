# Dashboard truth audit — 2026-05-28

Status: audit-only (no fixes applied in this pass)  
Scope: OrigenLab operator dashboard vs Gmail-derived SQLite, Postgres mirrors, classification logic, and known commercial cases.

---

## Executive summary

The dashboard codebase at **`main` @ `829e80d`** is **structurally safe for Tatiana** (read-only GET, no send/compose, `gmail_url` stripped in UI parsers, safety tests passing). **SQLite operational truth is largely consistent** with the five known cases (CEAF×SERVA, IKA RV10.70, CRTOP, SERVA logistics, bounces).

**Gaps that affect day-to-day usefulness:**

| Area | Verdict |
|------|---------|
| **Safety / privacy** | Good in code + tests; API not live-tested (server down locally). |
| **CEAF×SERVA deal + catalog** | SQLite amounts and `catalog_product_commercial_history` are correct; dashboard display fixed in recent commits (`8069f6e`, `9b1bab5`) but **requires running API against synced Postgres** for production parity. |
| **Warm-case classification** | Known regressions mostly **pass** on current SQLite (14d window); **IKA autoreply** misclassified as `supplier_quote_received`; **CRTOP threads duplicated** in queue. |
| **Licitaciones / equipment** | **Empty** — canonical `equipment_first_operator_queue_*.csv` missing under `reports/out/active/current`. |
| **Raw status tokens** | **Negocios** table still shows `logistics_pending`, `needs_review`, `reconciled_excluding_supplier_freight` without full Spanish labels. |
| **Postgres mirror** | **Not verified** this run (`ORIGENLAB_POSTGRES_URL` unset locally). |
| **Gmail freshness** | Canonical Gmail ingest: **1,132** messages, latest **2026-05-27**; full archive **216,714** rows (mixed mbox + Gmail). |

**Recommendation:** Tatiana can use the dashboard **for triage and read-only review** after a normal refresh (`DASHBOARD_FAST=1` + optional ingest + `RUN_COMMERCIAL_DEAL_MIRROR=1` + **catalog mirror sync**). Treat **Licitaciones** and **equipment opportunity counts on Hoy** as unreliable until the equipment CSV path is restored. Treat **Negocios** status columns as operator-unfriendly until Phase 9C label pass.

---

## 1. Git and environment preflight

| Check | Result |
|-------|--------|
| Branch | `main...origin/main` (clean at audit time) |
| HEAD | `829e80d` — feat(web): add script to export email signature assets |
| Recent catalog/commercial | `8069f6e` fix SERVA commercial history display · `9b1bab5` feat commercial history · `76288ad` catalog UX polish |
| Local API | **Not reachable** on `127.0.0.1:8001` |
| `ORIGENLAB_SQLITE_PATH` | `~/data/origenlab-email/sqlite/emails.sqlite` (**present**, ~128 GB) |
| `ORIGENLAB_POSTGRES_URL` | **Not set** in audit environment |

Uncommitted work was not modified during this audit.

---

## 2. Dashboard route inventory

| Route | Page | Primary APIs | Data source | Notes |
|-------|------|--------------|-------------|-------|
| `#/` | Hoy | `/health`, `/operator/status`, `/cases/warm`, `/opportunities/equipment`, `/mirror/commercial/deals`, `/mirror/catalog/products` | SQLite warm + equipment CSV; Postgres mirrors for deals/catalog | KPI cards derived from warm presets + deal blockers; equipment count **0** if CSV missing |
| `#/inbox` | Bandeja de revisión | `/cases/warm` (14d, limit 100) | SQLite | Presets: oportunidades, proveedores, pagos, logística; drawer strategy labels in Spanish |
| `#/opportunities` | Oportunidades | `/cases/warm`, `/opportunities/equipment` | SQLite + CSV | Equipment section empty in audit |
| `#/deals` | Negocios | `/mirror/commercial/deals` | Postgres `commercial.deal` | Highlight cards translate some statuses; **table uses raw tokens** |
| `#/catalogo` | Catálogo | `/mirror/catalog/products`, `.../{product_key}` | Postgres `catalog.*` | 9 products; SERVA uses `commercial_history` in SQLite (mirror after sync) |
| `#/suppliers` | Proveedores | `/cases/warm` (filtered) | SQLite | Entity grouping by supplier domain |
| `#/tenders` | Licitaciones | `/opportunities/equipment` | CSV mirror | **Reduced mode / empty** |
| `#/payments-logistics` | Pagos y logística | `/cases/warm` (pagos/logística presets) | SQLite | SERVA payment/logistics cases surface here |
| `#/contacts` | Contactos | `/contacts/{email}` on demand | SQLite | Profile load per selection |
| `#/system` | Sistema | `/health`, `/operator/status` | SQLite path metadata | Shows verdict/warnings; `sqlite_path` in API response (parser does not surface in UI) |

**Row click / drawer:** Catalog, inbox, suppliers, contacts use drawers; deals are table-only (no product deep-link yet).

**Forbidden fields in UI code:** Parsers null `gmail_url` and strip forbidden keys (`commercialParse`, `catalogParse`, `commercialDealsParse`). Static safety tests enforce no `mailto` compose and no legacy write routes.

---

## 3. API endpoint audit (code + SQLite-backed logic)

Live HTTP calls were **not** possible (API down). Findings combine **repository behavior**, **unit tests (46 API + 227 dashboard passed)**, and **SQLite probes**.

| Endpoint | Expected | Audit result |
|----------|----------|--------------|
| `GET /health` | 200, backend hint | Not live-tested |
| `GET /operator/status` | verdict, warnings, sqlite_path | Not live-tested; drives Hoy banner |
| `GET /cases/warm` | items + meta, read_only | **38 items** (14d, `include_noise=false`); categories below |
| `GET /opportunities/equipment` | items or reduced_mode | **0 items**, `reduced_mode=true`, CSV not found |
| `GET /mirror/commercial/deals` | redacted deals | SQLite has **1 deal** with expected CLP/EUR totals |
| `GET /mirror/catalog/products` | 9 products | SQLite **9** products, **4** `commercial_history` rows |
| `GET /mirror/catalog/products/{key}` | detail + `commercial_history` | SERVA keys have client CLP + supplier EUR lines in SQLite |

**Warm-case category mix (14d, default queue):**

- `client_opportunity`: 13  
- `supplier_quote_received`: 12  
- `deal_evidence_candidate`: 5  
- `supplier_followup`: 3  
- `logistics_admin`: 2  
- `payment_admin`: 2  
- `client_response`: 1  
- `bounce_problem`: **0** (bounces only appear with `include_noise=true`)

**Joined-prose guard:** API/catalog tests enforce repair of legacy artifacts; `enelectroforesis` repair added in `8069f6e` path (API `catalog_mirror_safety` + dashboard `catalogParse`).

---

## 4. Gmail vs SQLite comparison

| Metric | Value |
|--------|--------|
| Total `emails` rows | 216,714 |
| Canonical Gmail (`source_file LIKE 'gmail:contacto@origenlab.cl/%'`) | 1,132 |
| Latest canonical `date_iso` | 2026-05-27 |
| Rows with `date_iso > 2027` | 4 (data-quality outliers) |
| `mailer-daemon` / postmaster-like senders (broad) | 31,810 (historical archive, not all in 14d warm queue) |

**Interpretation:** Warm queue is driven by **recent enriched cases**, not the full 216k mbox archive. Canonical Gmail ingest is a **subset**; operator should not assume every historical thread appears in Bandeja.

---

## 5. Classification mismatch table (known cases)

| Evidence (redacted) | SQLite / warm category | Dashboard page | Expected | Actual | Severity | Proposed fix |
|----------------------|------------------------|----------------|----------|--------|----------|--------------|
| CEAF OC 26172 / Factura 6 | `deal_evidence_candidate`, `payment_admin` | Negocios, Pagos | Deal evidence + payment | Matches | — | — |
| SERVA proforma A2602545 / PO 174-26 | `deal_evidence_candidate`, supplier threads | Catálogo, Proveedores | Supplier quote + deal link | Catalog history in SQLite OK | — | Ensure Postgres catalog sync after seed build |
| BlueSlick/TEMED client nets | `commercial_deal_line` + `catalog_product_commercial_history` | Catálogo | Sold history, not “sin oferta” | Fixed in UI code `8069f6e` | — | Deploy + mirror sync |
| IKA Beatriz RV10.70 quote 112 | `supplier_quote_received` | Bandeja, Proveedores | `supplier_quote_received` | Matches | — | — |
| RG Energía / LabDelivery forward | `client_opportunity` (fwd) | Bandeja, Oportunidades | `client_opportunity` / forwarded | Matches | — | Optional: `forwarded_client_opportunity` label |
| IKA “Resposta automática” | **`supplier_quote_received`** | Bandeja | `auto_reply` / `system_noise` | Wrong | **P1** | Sender/subject rule in warm classification |
| CRTOP USD 10,600 EXW | `supplier_quote_received` (×6 threads) | Bandeja, Catálogo | `supplier_quote_received` | Category OK; **duplicate rows** | **P2** | Thread/case dedup by `thread_id` or supplier+subject key |
| Sebastian “Re: serva” | `internal_admin` | Bandeja (noise preset) | Internal / payment context | Matches | — | — |
| SERVA “Automatic reply” | `system_noise` | Hidden unless noise | Auto-reply | Matches | — | — |
| Mail Delivery Subsystem failure | `bounce_problem` (with noise) | Not in default 14d | `bounce_problem` | Matches when noise on | — | Keep default `include_noise=false` |
| DHL / logistics (SERVA) | `logistics_admin` | Pagos y logística | `logistics_admin` | Matches | — | — |

---

## 6. Page-by-page findings

### Hoy
- Counts derive from warm presets + commercial deals + catalog list length.
- **Useful:** surfaces client vs supplier vs pagos/logística split.
- **Misleading today:** “Licitaciones/equipos” card **0** when CSV missing; does not distinguish “no tenders” vs “pipeline broken”.
- Deal blockers count uses `margin_blockers.length` on mirror deals — aligns with SERVA Wise/DHL blockers when mirror synced.

### Bandeja de revisión
- Spanish category labels via `operatorLabels.ts`.
- Default queue **excludes** bounces and most `internal_admin` (46 rows only with `include_noise=true`).
- Drawer “Próxima acción” text is contextual (observed in API sample for CRTOP/IKA).
- **Risk:** CRTOP duplicate rows inflate perceived workload.

### Oportunidades
- Depends on warm client_opportunity + equipment API — equipment **empty**.

### Negocios (CEAF×SERVA)
**SQLite truth (verified):**

| Field | SQLite value |
|-------|----------------|
| Client net (lines) | 695k + 545k + 20k shipping = **1,260,000** |
| Client gross | **1,499,400** |
| Payment received | **1,499,400** |
| Supplier invoice total | **EUR 363.00** |
| Supplier paid | **EUR 218.00** |
| Product supplier cost (aggregate) | **EUR 148.00** (117+31) |
| Handling + freight (deal costs) | EUR 70 + EUR 145 (not on product unit prices) |

- `deal_status`: `logistics_pending` (not compound seed string).
- Highlight cards: “Logística pendiente” / “Requiere revisión”.
- **Table columns** still show raw `reconciliation_status`, `freight_status` tokens — **P1 UX**.
- Product line summaries in mirror should include BlueSlick + TEMED when `commercial_product` join populated (SQLite `product_id` set).

### Catálogo
- SQLite: 9 products; SERVA history rows correct (695k/545k CLP, EUR 117/31).
- Recent UI: “Último dato comercial”, Historial comercial, no “Sin oferta” for sold SERVA (`8069f6e`).
- CRTOP/IKA: supplier quote snapshots; IKA currency null — “Moneda pendiente” in tests.
- Prose: seed text has “en electroforesis”; repair guards `enelectroforesis` if mirror stored broken text.

### Proveedores
- Groups warm cases by supplier entity; SERVA/IKA/CRTOP appear from warm queue.
- Does not replace catalog commercial history for sold consumables.

### Pagos y logística
- CEAF bank-request and SERVA payment threads classify as `payment_admin` / deal evidence.
- No bank account numbers observed in classification strings (subjects only).

### Contactos
- On-demand profile; forbidden keys stripped in `contactParse`.

### Sistema
- Read-only policy messaging; health/status for operator trust.

### Licitaciones
- **Blocked:** equipment opportunities reduced mode — canonical CSV absent.

---

## 7. Data freshness

| Layer | Freshness signal |
|-------|------------------|
| SQLite canonical Gmail | Latest **2026-05-27** |
| SQLite file mtime | **2026-05-27** (local) |
| `catalog_*` / `commercial_deal` | Present; history **4** rows |
| Postgres mirror | **Not verified** this run |

**Suggested operator refresh (no deploy):**

```bash
cd apps/email-pipeline
DASHBOARD_FAST=1 \
RUN_GMAIL_INGEST=1 \
GMAIL_SINCE_DAYS=3 \
RUN_COMMERCIAL_DEAL_MIRROR=1 \
bash scripts/ops/refresh_render_dashboard_once.sh

# Catalog mirror is NOT in refresh_render_dashboard_once by default:
uv run python scripts/catalog/build_catalog_sqlite.py
uv run python scripts/sync/sync_catalog_postgres_mirror.py
uv run python scripts/qa/verify_catalog_postgres_mirror.py
```

Integrate catalog sync into daily fast refresh — **Phase 9D** recommendation.

---

## 8. Safety and privacy

| Check | Result |
|-------|--------|
| `gmail_url` in dashboard UI | Stripped to `null` in `commercialParse.ts` |
| Send / compose | No mounted send actions; `noWritePolicy` tests |
| Bank / RUT / IBAN in parsers | Forbidden patterns blanked |
| Warm-case API | Returns `gmail_url` in schema but UI does not render |
| Raw email bodies | Not in dashboard types; SQLite has `body` — not exposed via API parsers reviewed |

**Residual risk:** Operator status API includes `sqlite_path`; ensure production builds do not log full API JSON in browser devtools to untrusted parties.

---

## 9. UX / Spanish clarity

**Translated in places:** warm categories, deal highlight statuses, catalog money/dates, margin blockers text.

**Still raw in UI (P1/P2):**

- `logistics_pending`, `needs_review`, `reconciled_excluding_supplier_freight`, `dhl_account_or_external_freight`
- `deal_evidence_candidate`, `supplier_quote_received` (as category keys in some tables)
- `paid_by_client__supplier_payment_sent__logistics_pending` (catalog history seed only; SQLite deal uses shorter status)

---

## 10. Priority fix list

### P0 — correctness / safety
1. Restore **equipment opportunities CSV** path or Postgres mirror so Licitaciones/Oportunidades are not falsely empty.
2. Confirm **Postgres mirror sync** in operator environment after SQLite changes (deals + catalog).
3. Keep **`include_noise=false`** default on Bandeja (bounces stay out).

### P1 — business-misleading
4. Classify **IKA autorespuestas** as `system_noise` / `auto_reply`, not `supplier_quote_received`.
5. **Spanish labels** for all deal table status columns (match highlight cards).
6. **Dedup warm cases** per thread/supplier subject (CRTOP ×6).
7. **Negocio destacado:** show both BlueSlick and TEMED in product line summary when mirror synced.

### P2 — UX polish
8. Hoy: distinguish “equipment feed unavailable” vs “zero tenders”.
9. Catalog: clarify “Historial de precios” when `commercial_history` exists (already partially addressed).
10. Deals → Catálogo deep links for SERVA products.

### P3 — nice-to-have
11. `forwarded_client_opportunity` as visible category chip.
12. Today: “waiting on supplier / client / logistics” buckets.
13. Integrate catalog mirror into `refresh_render_dashboard_once.sh`.

---

## 11. Suggested next phases

| Phase | Focus |
|-------|--------|
| **9B** | Classification fixes (IKA autoreply, CRTOP dedup, bounce preset docs) |
| **9C** | Dashboard UX — raw token translation, deals table, equipment empty state |
| **9D** | Refresh orchestration — catalog + commercial deal mirror in fast path |

---

## 12. Tests run (read-only)

| Command | Result |
|---------|--------|
| `cd apps/api && uv run pytest tests/mirror/test_mirror_catalog.py tests/mirror/test_mirror_commercial_deals.py tests/test_cases_warm_output_normalize.py -q` | **46 passed** |
| `cd apps/dashboard && npm test` | **227 passed** |
| `cd apps/dashboard && npm run build` | **OK** |
| `cd apps/email-pipeline && uv run pytest tests/test_warm_case_role_classification.py tests/test_warm_case_sender_rules.py tests/test_catalog_seed.py tests/test_catalog_postgres_mirror.py -q` | **38 passed** |

---

## 13. Top 10 discrepancies

1. **Equipment/tenders feed empty** — CSV missing; dashboard shows 0 opportunities.  
2. **Postgres mirror not verified** locally — production may differ from SQLite.  
3. **IKA autoreply** classified as supplier quote.  
4. **CRTOP duplicate warm rows** (same quote thread).  
5. **Negocios table raw status tokens** (`reconciliation_status`, `freight_status`).  
6. **Archive vs canonical Gmail** — 216k vs 1.1k Gmail rows (scope confusion risk).  
7. **`deal_status` in SQLite** is `logistics_pending` only — catalog history uses longer compound string.  
8. **API not running** during audit — live JSON forbidden-field scan not executed.  
9. **4 emails with future dates** in SQLite — may affect “latest” ordering edge cases.  
10. **Catalog mirror** not part of default dashboard refresh script.

---

## 14. Top 10 recommended fixes

1. Restore/generate `equipment_first_operator_queue_*.csv` under active/current.  
2. Run full mirror sync (dashboard + commercial deals + catalog) before operator review.  
3. Fix IKA autoreply classification rule.  
4. Add warm-case deduplication by thread.  
5. Translate all deal table status fields to Spanish.  
6. Add “feed unavailable” empty state on Licitaciones/Hoy equipment card.  
7. Wire catalog sync into daily refresh orchestrator.  
8. Deals spotlight: list BlueSlick + TEMED with links to `#/catalogo`.  
9. Live API smoke script in CI (forbidden keys + prose artifacts).  
10. Document canonical Gmail scope on Sistema page (1.1k vs full archive).

---

## 15. Safe for Tatiana today?

**Yes, with caveats:** use for **read-only triage** of Bandeja, Negocios, and Catálogo **after mirror sync**. Do **not** rely on Licitaciones/equipment counts until CSV is restored. Treat duplicate CRTOP rows and IKA autoreply as known classification noise until Phase 9B.

---

*Machine-readable findings: [`reports/out/audits/dashboard_truth_audit_2026-05-28_findings.csv`](../../reports/out/audits/dashboard_truth_audit_2026-05-28_findings.csv)*
