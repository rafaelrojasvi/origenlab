# Phase 9B — Warm-case classification and dedup fixes

Read-only follow-up to [DASHBOARD_TRUTH_AUDIT_2026-05-28.md](./DASHBOARD_TRUTH_AUDIT_2026-05-28.md). No Gmail mutation, no outreach writes, no production Postgres writes.

## Changes

### 1. Autoreply detection (PT / ES / DE / EN)

`warm_case_sender_rules.py` now treats supplier/client autoresponders as noise unless the preview contains real quote cues (price, stock, product model):

| Marker examples | Role |
|-----------------|------|
| `Resposta automática`, `Autorespuesta`, `Automatische Antwort` | `system_noise` |
| `Out of office`, `fuera de oficina`, vacation / office closed | `system_noise` |
| `Automatic reply`, `auto-reply` | `system_noise` (unchanged) |

**Before:** IKA `RES: Resposta automática: Cotización` → `supplier_quote_received` (matched weak `re:` / `cotiz` markers).

**After:** Same subject → `system_noise`; hidden from default queue (`include_noise=false`).

**Preserved:** Beatriz IKA RV10.70 with `Monto 112,00` / stock → `supplier_quote_received`.

### 2. API response-time override

`warm_case_output_normalize.py` reclassifies stored `supplier_quote_received` rows when autoreply text is present and there is no real quote content — fixes stale SQLite categories without DB writes.

### 3. CRTOP / supplier thread dedup

`warm_case_grouping.py` adds stable group keys:

- **RG Energía / IKA RV10.70** — unchanged thread hint.
- **CRTOP reactor** — `thread:crtop-reactor-olt-hp-5l` for `crtopmachine.com` + reactor inquiry subjects.

Promotion uses the same hints for `case_key`. The API collapses duplicate rows in `normalize_warm_case_items` and sets `grouped_email_count` on the primary row (latest `last_email_id`).

**Before:** ~6 dashboard rows for the same CRTOP reactor thread.

**After:** One row with `grouped_email_count` > 1 when duplicates exist; dashboard shows `×N` on the subject line.

### 4. Bounces

Mail Delivery Subsystem / `mailer-daemon` rows remain `bounce_problem` and are excluded unless `include_noise=true` (unchanged behavior, regression-tested).

## Regression matrix

| Fixture | Expected category |
|---------|-------------------|
| IKA `Resposta automática` | `system_noise` |
| Beatriz IKA RV10.70 + 112,00 | `supplier_quote_received` |
| RG Energía / LabDelivery forward | `client_opportunity` |
| Sebastian `Re: serva` | `internal_admin` |
| SERVA `Automatic reply` | `system_noise` (hidden default) |
| DHL / logistics | `logistics_admin` |
| Banco FACTURA | `payment_admin` |
| CRTOP reactor (6× same subject) | 1 row, `grouped_email_count` = 6 |

## Files touched

- `apps/email-pipeline/src/.../warm_case_sender_rules.py`
- `apps/email-pipeline/src/.../warm_case_role_classification.py`
- `apps/email-pipeline/src/.../warm_case_grouping.py` (new)
- `apps/email-pipeline/src/.../warm_case_promotion.py`
- `apps/api/src/.../warm_case_output_normalize.py`
- `apps/api/src/.../schemas/cases.py`
- `apps/dashboard/src/api/commercialTypes.ts`, `commercialParse.ts`, `WarmCasesTable.tsx`
- Tests under `apps/email-pipeline/tests/` and `apps/api/tests/`

## Verify

```bash
cd apps/email-pipeline && uv run pytest tests/test_warm_case_role_classification.py tests/test_warm_case_sender_rules.py tests/test_warm_case_promotion.py -q
cd apps/api && uv run pytest tests/test_cases_warm_output_normalize.py -q
cd apps/dashboard && npm test -- --run src/lib/warmCaseViewPreset.test.ts src/components/commercial/WarmCasesTable.test.tsx
```
