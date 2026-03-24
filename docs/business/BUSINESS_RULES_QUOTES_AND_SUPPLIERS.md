# Business rules: quotes (cotizaciones) and supplier research

Status: canonical  
Owner: project-maintainers  
Last reviewed: 2026-03-24

Formal rules and **proposed** data shapes for OrigenLab commercial work. This doc is **source of truth for policy**; Word templates remain **presentation**. When code or DB schemas exist, they must not contradict this file without an explicit decision and doc update.

**Related:** [`apps/web/docs/company-scope.md`](../../apps/web/docs/company-scope.md) (tone, contact, cotización prompts, [operational intake checklist](../../apps/web/docs/company-scope.md#datos-a-solicitar-operativo)).

---

## 1. Project-wide truth rule (non-negotiable)

**Do not send, publish, or generate commercial claims that are not confirmed** (or explicitly marked as *pending / not applicable*).

Concretely, unless **confirmed** or **explicitly flagged as unconfirmed**:

- Do **not** state or imply: specific **brands**, **warranties**, **stock**, **lead times**, **technical specifications**, **SLAs**, **exclusivity**, or **partnerships**.
- **Duplicate** master templates; **replace only** bracketed / placeholder fields; do **not** free-form add commercial facts.

This rule applies to: internal checklists, any future quote generator, LLM prompts, and DB-backed workflows.

---

## 2. Quote (cotización) policy rules

### 2.1 Template discipline

- Work from a **duplicated** master file; change **only** intended placeholders.
- **Provenance:** retain **intake source**, **template version**, **author**, and **generation timestamp** for every quote (once tooling exists).

### 2.2 “Ready to send” gates (target behavior)

Until enforced in software, these are **manual policy**; implement validation in a quote tool/DB when ready.

| Gate | Requirement |
|------|-------------|
| Minimum intake | Required client/request fields present (see §3). |
| Commercial terms | **Delivery**, **payment**, **validity**, **taxes (e.g. IVA)**, **warranty**, **installation/startup**: each is either a **confirmed value** or **explicit** “not confirmed” / “not applicable”. |
| Technical claims | **Model**, **brand**, **lead time**, **warranty** line items: **confirmed** or explicitly **not confirmed**. |
| Taxes | **Never inferred**; state inclusion/exclusion of IVA (or equivalent) explicitly. |

---

## 3. Quote request — intake field model (target)

The “ficha breve” is already a **logical data model**. These fields should eventually live in **structured storage** (DB or validated form), not only in `.docx`.

| Area | Fields (indicative) |
|------|---------------------|
| Organization | Company / institution name, RUT (if applicable), city, **region** |
| Contact | Name, **role / area**, email, phone |
| Need | Equipment type, **preferred brand** (if any), **exact model** (if known), **quantity** |
| Technical | **Application**, matrix/sample type, **required range / capacity**, accessories/consumables |
| Commercial | **Target purchase date**, **delivery place**, invoice requirements, **tender vs direct purchase**, **estimated budget** (optional) |
| Services | Installation, startup, training, support — **requested** vs **quoted** (later) |

**Minimum required for “quote started”** should be defined in implementation (subset of the above); this doc lists the **full** intended model.

---

## 4. Quote output structure (target document schema)

Repeatable sections from internal templates and examples:

| Block | Content |
|-------|---------|
| Header | Quote **number**, **date** |
| Parties | **Client**, institution/company, **contact** |
| Reference | Main reference (e.g. inquiry / RFQ id) |
| Summary | Short technical summary |
| Lines | **Quote items** (see §5) |
| Terms | **Delivery**, **payment**, **validity** |
| Legal/commercial | **Warranty** (as confirmed), **taxes / IVA** |
| Services | **Support**, **installation / startup** applicability |

---

## 5. Proposed core entities (quotes)

Names are logical; table names can differ in SQL.

### 5.1 `quote_request` (or equivalent)

What the client asked for. Links to intake fields (§3). Status: e.g. `draft`, `complete`, `converted_to_quote`.

### 5.2 `quote`

The commercial document sent (or ready to send). Links to `quote_request`, carries document metadata (number, date, template version, author, timestamps).

### 5.3 `quote_item`

Each line: description, qty, unit price (if applicable), references to SKU/model **only if confirmed**.

### 5.4 `commercial_terms`

Delivery, payment, validity, tax treatment, warranty text **as stated**, each with optional **confirmation flag** or “pending”.

### 5.5 `technical_confirmation` (or flags on line/quote)

Per scope: model confirmed, brand confirmed, lead time confirmed, warranty confirmed, installation/startup applies — **boolean or tri-state** (confirmed / not applicable / pending).

---

## 6. Supplier (proveedor) research — master vs campaign

### 6.1 Separation (critical)

| Kind | Meaning |
|------|---------|
| **Supplier master** | Relatively stable facts: identity, domain, country, categories, ongoing relationship notes. |
| **Supplier research run / campaign** | One sourcing exercise: methodology, scoring, **rankings**, regional quotas, “top 20/50”, quick-win lists, **snapshot date**. |

**Rankings and “top N” from a given date are snapshot outputs**, not permanent truth about a supplier. Store them under a **run id**, not as the only record for the supplier.

### 6.2 Scoring dimensions (repeatable methodology)

When ranking suppliers in a campaign, dimensions should be **data**, not only prose:

1. Category fit  
2. Export readiness  
3. Ease of contact  
4. Credibility / documentation  
5. Partnership potential for Chile / LATAM  

Campaign rows should store **score per dimension** and **total** (or rank), tied to **`research_run_id`**.

### 6.3 Supplier prospect fields (target)

**Identity & research:** company name, domain, country, region, covered categories, confidence, **evidence URLs**, **outreach route**, scores by dimension, total score, **excluded** (e.g. already known supplier) flag, free-text notes, **workflow status** (`new`, `shortlisted`, `contacted`, `in_validation`, `rejected`, `active_candidate`).

**Commercial validation (post-outreach):** Chile territory support, LATAM partnership possible, **MOQ**, aftersales/support, spare parts, exclusivity conditions, **QA / due diligence status**.

**Run metadata:** `research_run_id`, date, methodology version, **why prioritized**, **category gap** addressed, **pending diligence** list.

---

## 7. What should stay narrative (not DB columns)

Keep as report/template prose:

- Long executive summaries  
- Regional commentary  
- Strategic “why this category matters” essays  
- Polished CTAs and marketing copy  

Store **structured facts** (tables above) in the DB; **generate** narrative from them when needed.

---

## 8. Implementation roadmap (for engineers)

1. **Done in docs:** This file + links from `company-scope` and doc map.  
2. **Next (high value):** Schema migration + minimal UI or CSV workflow for **quote_request** + **confirmation flags**.  
3. **Next:** **supplier_research_run** + **supplier_prospect** tables (or append to existing leads SQLite with clear naming).  
4. **Enforcement:** Script or gate: **block “ready_to_send”** without required fields and explicit handling of unconfirmed terms.

---

## 9. Changelog

| Date | Change |
|------|--------|
| 2026-03-24 | Initial canonical rules + proposed entities (from internal template / ficha / supplier report analysis). |
