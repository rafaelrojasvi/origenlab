# Phase 7A — Warm-case classification audit

## Problem (pre-7A)

| Symptom | Root cause |
|---------|------------|
| Sebastian `Re: serva` → client / problem | Generic `^re:` → `client_reply`; internal Gmail not in operator list |
| Beatriz IKA quote → opportunity | `ika.net.br` missing from supplier domains; positive signal → `opportunity` |
| Payment/logistics → client | Legacy `infer_warm_case_category` mapped admin threads to `client_reply` (API normalized later) |
| Banco/DHL mixed with clients | Same; dashboard presets relied on API normalize pass |

## Architecture after 7A

```
SQLite queue row
  → infer_warm_case_role_category()   # role taxonomy (source of truth)
  → role_category_to_legacy_storage() # Postgres promotion CHECK
  → API normalize_warm_case_item()    # re-run role infer at response time
  → dashboard presets                 # filter by role category
```

## Role categories

`client_opportunity`, `client_response`, `supplier_quote_received`, `supplier_followup`, `payment_admin`, `logistics_admin`, `internal_admin`, `system_noise`, `bounce_problem`, `deal_evidence_candidate`, plus workflow: `quote_sent`, `waiting_supplier`, `waiting_client`.

## Sender/domain rules (`warm_case_sender_rules.py`)

- **Internal/admin emails:** `tvivancob@gmail.com`, `sebastian.rojas.vivanco@gmail.com`, `contacto@origenlab.cl`, `contacto@labdelivery.cl`
- **Suppliers:** `serva.de`, `ika.net.br`, `ortoalresa.com`, `dhl.com`, `ollital.com`, `dlabsci.com`, `crtopmachine.com`, `hielscher.com`, `asynt.com`, `yuanhuai.com`, …
- **System/noise:** `no-reply@accounts.google.com`, `mailer-daemon@googlemail.com`

## Tests

`apps/email-pipeline/tests/test_warm_case_role_classification.py` — regression cases from operator audit.

## Not changed in 7A

- Postgres `commercial.warm_case` CHECK (legacy category strings on promote).
- Dashboard route structure (see Phase 7B design doc).
- Gmail ingest, sends, outreach writes.
