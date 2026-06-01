# Institution alias policy

Status: canonical (decision checkpoint)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-01

Related: [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md) · [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md) · [`../scripts/qa/audit_institution_grouping.py`](../scripts/qa/audit_institution_grouping.py)

Read-only review artifacts (gitignored, not committed):  
`reports/out/active/current/institution_alias_seed_review_2026_06_01/`

---

## 1. Current decision

| Topic | Decision |
| --- | --- |
| **Production `institution_alias` table** | **Do not create yet.** No DDL, no SQLite/Postgres writes, no automatic merge. |
| **Grouping for explorer** | **Domain-primary** cards from `contact_master` / `organization_master` are reliable enough for a **read-only institution explorer**. |
| **Alias seeds** | **Proposed / manual-review only.** Audit output (`alias_seed_candidates.csv`, review CSVs) is a queue — not operational truth. |
| **Send gates** | Aliases **must never** feed outbound safety. Sending stays on `contact_email_suppression`, `contact_domain_suppression`, `outreach_contact_state`, and export gates (golden rule in [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md)). |
| **Scope of aliases** | **Explorer / read-model display only** — optional future grouping of domain cards under a canonical name. No contact merge, no send approval, no suppression bypass. |

---

## 2. Manual review outcome (2026-06-01)

Source: institution grouping audit → 133 proposed seeds → conservative manual review pack.

| Outcome | Count | Share |
| --- | ---: | ---: |
| Proposed seeds reviewed | 133 | 100% |
| **approve_candidate** | 34 | ~26% |
| **rejected** (noise / platform / supplier) | 66 | ~50% |
| **needs_business_review** | 33 | ~25% |

**Why no production alias table yet:** only **~26%** passed conservative auto-review. The majority are ESP/platform, free-mail, lab-equipment vendors, generic tokens, or ambiguous conglomerates. An alias map built from unreviewed seeds would create false institution merges.

---

## 3. Safe rules (approve / reject)

### Approve only when

- Same **brand stem** across **`.cl` + `.com`** (or `mail.` / `correo.` subdomain of the same registrable domain).
- **Registrable-domain evidence** — never alias from **normalized org name alone**.
- No `supplier_flag`, no known vendor/catalog domain, no platform/ESP pattern.
- No suspicious TLD mix (`.site`, `.ga`, `.ml`, `.cf`, typo TLDs like `.cli`).

### Reject when

- **ESP / bulk-mail** (`impactomail`, `enviosmasivos`, …).
- **Platform / free-mail** (`hotmail`, `outlook`, `wetransfer`, `jooble`, …).
- **Lab-equipment vendors** — keep on **supplier path**, not buyer institution alias.
- **Generic normalized keys** (`service`, `admin`, `info`, `domain`, …).
- **Phishing / spam TLD clusters** (multi-`.cc`/`.website` without stable `.cl`/`.com`).

### Needs business review when

- **Conglomerates** with department subdomains (e.g. CMPC facilities).
- **Banks / public sector** (mixed legit mail + suspicious senders).
- **Pharma / large vendors** where buyer vs supplier role is unclear.
- **Healthcare / university** networks (facility vs parent org scope).

### Always

- **Supplier/vendor stays separate** from buyer institution KPIs and alias seeds.
- **Aliases affect display only** — never `candidate_export_gate`, NDR apply, or outreach state.

---

## 4. Examples

### Approved candidates (conservative shortlist)

| Institution | Pattern | Notes |
| --- | --- | --- |
| **Bureau Veritas** | `bureauveritas.cl` + `bureauveritas.com` + `cl.bureauveritas.com` | Clear corporate brand across TLDs |
| **Lactalis** | `lactalis.cl` + `cl.lactalis.com` | Food corporate `.cl`/`.com` pair |
| **Smurfit Kappa** | `smurfitkappa.cl` + `smurfitkappa.com` | Packaging brand pair |
| **Austral Biotech** | `australbiotech.cl` + `australbiotech.com` | Chile biotech pair |
| **Oxiquim** | `oxiquim.cl` + `oxiquim.com` | Chemical corporate pair |

### Rejected (do not seed)

| Label | Why |
| --- | --- |
| **Hotmail** | Free-mail / webmail — not an institution |
| **Labtron** | Multi-exotic-TLD vendor spam cluster |
| **Labotronics** | Lab-equipment supplier — supplier path |
| **Mailaa** | ESP/webmail-style infrastructure |
| **Eshopex** | Third-party logistics/platform sender |

### Needs business review

| Label | Why |
| --- | --- |
| **CMPC** | Multiple department subdomains — scope = business unit? |
| **Falabella** | Retail conglomerate + corporate mail subdomain |
| **Banco Falabella / Scotiabank / HSBC** | Financial entities — confirm relationship type |
| **Merck / AstraZeneca** | Pharma vendor vs customer ambiguity |

---

## 5. Future path (ordered)

1. **Manual sign-off** — operator reviews `approved_alias_seed_candidates.csv` from the latest review pack; reject or defer rows freely.
2. **Tiny proposed alias store (maybe)** — e.g. a versioned CSV or table with `status=proposed|approved|rejected` — only after explicit approval; still no send coupling.
3. **Read-only institution explorer** — optional UI that groups domain cards by approved alias; confidence badges; no write actions.
4. **Never** — connect aliases to outbound safety, suppression sidecars, or automatic contact merge.

Re-run grouping audit after blocklist/seed changes:

```bash
uv run python scripts/qa/audit_institution_grouping.py --date-label YYYY_MM_DD
```

---

## 6. Do not change without explicit approval

- SQLite / Postgres **schemas** for `institution_alias` or merged contacts
- Send/export gate logic keyed on alias or institution classification
- Automatic promotion of audit `alias_seed_candidates.csv` to production truth
