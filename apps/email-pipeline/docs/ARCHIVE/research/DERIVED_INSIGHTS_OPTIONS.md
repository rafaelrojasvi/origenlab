# What else can be derived from the email reports? (archived full text)

Status: archived  
Replaced by: `../../reporting/OUTPUTS_OVERVIEW.md` (section **Future derived insights (backlog)**)  
Archived on: 2026-03-24  
Why archived: merged into outputs doc + backlog table; full narrative kept here for reference.

---

Based on the current reports (business filter summaries, category counts, sender domains, unique_emails, scope/summary with aggregates), these are **additional relationships and outputs** that are feasible with the same data (subject, body, sender, recipients, date).

## Already in the reports

- **Volume & time:** total messages, by year, by year for “cotización”
- **Classification:** primary_category + tags (internal, institution, business_core, logistics, etc.), category counts
- **Sender side:** top sender domains by view (all / operational_no_ndr / business_only / business_only_external), top raw senders
- **Signals in text:** aggregates for cotización, universidad, factura, pedido/OC, bounce-like, and **equipment** (eq_balanza, eq_centrifuga, etc.)
- **Cotización ∧ equipment:** cotiz_balanza, cotiz_microscopio, etc. (already in `generate_client_report` SQL)
- **Unique emails:** who appears as sender and/or in recipients, with counts

## 1. Equipment ↔ University / institution

**Idea:** Which equipment types are most mentioned in traffic with universities (or institution-tagged senders)?

**Output examples:** Table: domain × equipment counts; or universities rollup → top equipment.

**What you need:** Per message: sender domain + eq_* and universidad/institution signals (same LIKE logic as `_merged_aggregate_sql()`).

## 2. Equipment ↔ sender domain (any domain)

**Idea:** Per sender domain, how many messages mention each equipment type (or cotización ∧ equipment).

## 3. University / institution relations (summary)

**Idea:** Domains that count as university/institution, with message count and optionally top equipment.

## 4. Domain type / sector

**Idea:** Classify sender domains (university, government, supplier, logistics, marketplace, other), then volume and equipment mix per type.

## 5. Recipient / contrapartes

**Idea:** Top domains in To/Cc (excluding own domain). `unique_emails.csv` has `count_in_recipients`; extend with domain aggregation if needed.

## 6. Equipment by year

**Idea:** Time trend of equipment mentions (and optionally cotización ∧ equipment by year).

## 7. Supplier / brand ↔ equipment

**Idea:** Map supplier domains to equipment families; count co-occurrence in threads.

## 8. Equipment co-occurrence

**Idea:** Pairs of equipment types in the same message (heatmap / pair counts).

## 9. Model / brand mentions by domain or sector

**Idea:** Extend `email_ml_explore.py` regex output with per-domain or per-sector aggregation.

## Summary table (original)

| Derived output | Main use | Effort |
|----------------|----------|--------|
| Equipment × university | Uni / institution equipment themes | 1 pass + domain + LIKE |
| Equipment × domain | Per-sender equipment mix | Same |
| University relations | List unis + volume + top equipment | Domain list + pass |
| Domain type / sector | Segment reporting | Domain→sector map |
| Recipient domains | Who we send to | Parse recipients |
| Equipment by year | Trends | GROUP BY year + LIKE |
| Supplier ↔ equipment | Supplier×equipment | Domain→brand map |
| Co-occurrence | Bundles / pairs | Per-message eq set |
| Models by domain | Regex + domain | Extend ml explore |

## Suggested order (original)

1. Equipment × domain and Equipment × university  
2. University relations  
3. Recipient / contrapartes  
4. Domain type / sector  
5. Equipment by year  
6. Supplier ↔ equipment and co-occurrence  
