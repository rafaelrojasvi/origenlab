# Business-only filtering layer

## What problem this solves

The email archive mixes **real commercial traffic** (quotes, orders, suppliers, customers) with **noise**: newsletters, social notifications, bounces (NDR), spam, and automated platform messages. Client-facing analysis and ML become noisy when all of this is treated the same.

This layer tags each email into **operational buckets** and exposes filtered views so downstream reports and models can work on a **business-only** slice.

---

## Category definitions

| Category | Meaning | Examples |
|----------|---------|----------|
| **bounce_ndr** | Delivery failure / non-delivery report | Mailer-Daemon, postmaster, “delivery failed”, “undeliverable” |
| **spam_suspect** | Heuristic spam hints | Adult/promo subject patterns, common scam phrases |
| **social_notification** | Social platform mail | facebookmail.com, linkedin.com, twitter.com |
| **newsletter** | Marketing / bulk | newsletter@, noreply@, “unsubscribe”, “promo” |
| **logistics** | Shipping / couriers | dhl.com, fedex, correos.cl, tracking |
| **marketplace** | Tenders / public procurement | mercadopublico.cl, wherex.com, licitación |
| **institution** | Universities, public bodies | uach.cl, uc.cl, .edu, “universidad” in body |
| **internal** | Own company | labdelivery.cl, origenlab.cl |
| **supplier** | Known supplier domains (config) | Set in `business_filter_rules.SUPPLIER_DOMAINS` |
| **customer** | Known customer domains (config) | Set in `business_filter_rules.CUSTOMER_DOMAINS` |
| **business_core** | Generic commercial signal | cotización, quote, factura, pedido, orden de compra, adjunto, plazo, stock |
| **unknown** | No rule matched | Fallback |

When primary is **business_core**, an optional **commercial_subtype** is set when subject/body match: `quote`, `order`, `invoice`, `support`, or `followup` (first match in that order). Used for finer breakdown only; the main views do not depend on it.

---

## Precedence

When several categories match, **one primary category** is chosen by this order (first match wins):

1. bounce_ndr  
2. spam_suspect  
3. social_notification  
4. newsletter  
5. logistics  
6. marketplace  
7. institution  
8. internal  
9. supplier / customer / business_core  
10. unknown  

All matching tags are still stored in `tags`; `primary_category` is the one used for counts and views.

---

## How business_only is defined

- **business_only** (include internal):  
  - Includes: business_core, supplier, customer, institution, logistics, marketplace, **and** internal.  
  - Excludes: bounce_ndr, spam_suspect, social_notification, newsletter.

- **business_only_external**:  
  - Same as above but **excludes** internal (only external commercial/operational mail).

- **operational_no_ndr**:  
  - All messages except bounce_ndr (no other exclusions).

- **all_messages**:  
  - No filtering.

---

## Limitations

- **Rule-based only**: No ML or LLM. False positives/negatives are possible (e.g. a newsletter that looks like a quote).
- **Language**: Patterns are tuned for Spanish + English (e.g. cotización, factura, orden de compra).
- **Supplier/customer**: Only applied if you populate `SUPPLIER_DOMAINS` and `CUSTOMER_DOMAINS` in `business_filter_rules.py`.
- **No temporal logic**: No “first contact” or thread-level logic; each message is classified in isolation.

---

## How to extend rules safely

1. **Domain lists**: Edit `src/origenlab_email_pipeline/business_filter_rules.py`. Add domains to the right list (e.g. `LOGISTICS_DOMAINS`, `INSTITUTION_DOMAINS`, `INTERNAL_DOMAINS`). Use lowercase; matching is substring/prefix (e.g. `uach.cl` matches `mail.uach.cl`).
2. **Keyword patterns**: Add to the relevant `*_PATTERNS` list (sender, subject, or body). Patterns are lowercased and checked with `in` (substring).
3. **New category**: Add a new list and a check in `email_business_filters.classify_email`, then append the category to `CATEGORY_PRECEDENCE` in the desired position.
4. **Precedence**: To give a category priority, move it earlier in `CATEGORY_PRECEDENCE`. Run tests after changes: `uv run pytest tests/test_email_business_filters.py -v`.

---

## Artifacts

When you run the business filter (standalone script or client report with `--with-business-filter`), the following are written:

| File | Content |
|------|---------|
| `business_filter_summary.json` | Counts by primary category, rollup flags, view counts, top sender domains/senders per view |
| `business_only_sample.json` | Sample of messages in the business_only view (id, sender, subject, tags) |
| `category_counts.csv` | One row per category, count |
| `sender_domain_by_view.csv` | view, domain, count |

---

## Commands

```bash
# Standalone: full pass, write artifacts to default reports folder
uv run python scripts/reports/generate_business_filter_report.py

# With output dir and row limit (faster)
uv run python scripts/reports/generate_business_filter_report.py --out reports/out/bf --limit 50000

# Client report including business filter section (full or sampled)
uv run python scripts/reports/generate_client_report.py --with-business-filter
uv run python scripts/reports/generate_client_report.py --with-business-filter --business-filter-sample 30000
```

---

## Exact vs heuristic vs exploratory

In the client report, the **“Exact vs Heuristic vs Exploratory”** section states:

- **Exact**: Counts tied to DB rows and dates (e.g. total messages, by year).
- **Heuristic**: Rule-based tags (these business categories); not ground truth.
- **Exploratory**: Clusters/embeddings on samples; for discovery only.

Business filter outputs are **heuristic**: interpret them as “likely” business vs noise, not as verified labels.
