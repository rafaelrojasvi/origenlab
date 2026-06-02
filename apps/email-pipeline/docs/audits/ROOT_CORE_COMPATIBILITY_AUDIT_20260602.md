# Root vs core compatibility module audit — Phase 5H

**Status:** read-only audit (no code changes)  
**Date:** 2026-06-02  
**Scope:** `src/origenlab_email_pipeline/*.py`, `src/origenlab_email_pipeline/core/**/*.py`, `scripts/**/*.py`, `apps/business_mart_app.py`, `apps/api` (email-pipeline imports), `tests/**/*.py`, live docs that reference import paths  
**Authority:** [`QUALITY_AND_REFACTOR_STRATEGY.md`](../QUALITY_AND_REFACTOR_STRATEGY.md), [`docs/pipeline/PACKAGE_DOMAINS.md`](../pipeline/PACKAGE_DOMAINS.md), [`docs/README.md`](../README.md), [`tests/test_core_import_surface.py`](../../tests/test_core_import_surface.py)

**Related:** [`CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md), [`STREAMLIT_RETIREMENT_AUDIT_20260602.md`](STREAMLIT_RETIREMENT_AUDIT_20260602.md) (Phases 5E–5G completed separately)

---

## Executive summary

The **`core/` tree is not a second implementation layer** for the modules investigated here. It is a **Stage 2A/2B stable re-export surface**: almost every `core/*` file is an **8–12 line shim** that `from … import *` from the matching **top-level root module**, which still holds **100% of the runtime logic**.

| Pattern | Count | Classification |
|---------|-------|----------------|
| Root module = implementation | 29 investigated pairs | **A** (canonical) |
| `core/*` sibling = re-export shim | 29 investigated pairs | **B** (compatibility) |
| Logic extracted **into** `core/` only (no root twin) | 9 modules | **A in core** |
| Root `commercial_intel_*` → `commercial/` | 4 modules | **B** (subpackage shims) |

**Import reality (email-pipeline + apps/api, `.py`/`.md`/`.sh`, 2026-06-02):**

- **Root** `origenlab_email_pipeline.<module>` references dominate (**15–145 files** per high-fan-in module).
- **Production** `origenlab_email_pipeline.core.*` references are **rare** (~**21** `.py` files total, mostly mart build extraction, DNR/broad-lane helpers, safety, and `test_core_import_surface.py`).
- **`apps/api`** imports **root paths only** (`config`, `db`, `contacto_gmail_source`, `outbound_core`, `business_mart`) — no `core.*` usage.

**Phase 5H recommendation:** **Do not delete any root/core pair in Phase 5.** Removing root modules would break the package; removing `core` shims would collapse the documented import surface. This work belongs to **Stage 6C+ vertical migration** (one domain per PR, tests + docs), not to the script/Streamlit retirement track (5A–5G).

**`__pycache__`:** `git ls-files '*__pycache__*'` returns **empty** — no tracked cache clutter to remove.

---

## Classification legend

| Code | Meaning |
|------|---------|
| **A** | Canonical active implementation (real logic lives here) |
| **B** | Compatibility shim (re-export only; no independent behavior) |
| **C** | Old duplicate still imported (both paths actively used with different semantics) |
| **D** | Safe removal candidate (strong evidence, low fan-in, tests exist) |
| **E** | Unsafe / safety-critical — do not remove without explicit migration plan |

---

## Architecture model (current truth)

```
scripts/ / business_mart_app / apps/api / most tests
        │
        ▼  (dominant today)
origenlab_email_pipeline.<root_module>     ← A: implementation (~57–851 LOC)
        ▲
        │  from ..<root> import *
origenlab_email_pipeline.core.<domain>.<root_module>   ← B: shim (~8 LOC)
        ▲
        │  (preferred for *new* code per docs; not mass-migrated yet)
new scripts / core.mart.build_runner / process_broad_marketing_contacts
```

**Exceptions — canonical logic already in `core/` (no root twin):**

| Module | LOC (approx) | Notes |
|--------|--------------|-------|
| `core/outbound/broad_marketing_contacts.py` | ~865 | Stage 6C1 extract from volume lane script |
| `core/outbound/do_not_repeat_master.py` | ~296 | Stage 6C2 extract from DNR export script |
| `core/research_automation.py` | ~1,683 | Deep research batch automation |
| `core/reports_out.py` | ~272 | `reports/out` bucket classification |
| `core/safety.py` | (small) | Env redaction / script deprecation helpers |
| `core/mart/build_runner.py` | ~200+ | Mart build orchestration (used by `build_business_mart.py`) |
| `core/mart/build_options.py` | | Mart build options dataclass |
| `core/mart/contact_org_builder.py` | | Contact/org rebuild |
| `core/mart/document_master_builder.py` | | Document master rebuild |
| `core/mart/opportunity_signal_builder.py` | | Opportunity signals rebuild |

These are **A in core**, not duplicates of root files.

---

## Duplicate pairs — infrastructure

| Root module | Core shim | Root LOC | Core LOC | Root import files | Core import files | Root class | Core class | Phase 5 |
|-------------|-----------|----------|----------|-------------------|-------------------|------------|------------|---------|
| `db.py` | `core/db.py` | 236 | 8 | **76** | 1 | **A / E** | **B** | **Keep both** — SQLite foundation; `init_schema` owns archive DDL |
| `config.py` | `core/config.py` | 118 | 12 | **145** | 2 | **A / E** | **B** | **Keep both** — highest fan-in module |
| `sqlite_migrate.py` | `core/sqlite_migrate.py` | 82 | 8 | **15** | 1 | **A / E** | **B** | **Keep both** — layered schema orchestration |

**`apps/api` root imports:** `config` (settings, mirror deps), `db.init_schema` (parity script), `contacto_gmail_source` (mirror tests).

**Tests locking behavior:** `test_build_business_mart.py`, `test_build_business_mart_phase2.py`, `test_sqlite_migrate.py`, `test_workspace_gmail_imap_ingest.py`, `test_sync_dashboard_postgres_mirror.py`, `test_core_import_surface.py`.

---

## Duplicate pairs — Gmail

| Root module | Core shim | Root LOC | Core LOC | Root import files | Core import files | Root class | Core class | Phase 5 |
|-------------|-----------|----------|----------|-------------------|-------------------|------------|------------|---------|
| `gmail_send.py` | `core/gmail/gmail_send.py` | 133 | 8 | **4** | 1 | **A / E** | **B** | **Keep both** — send path |
| `gmail_workspace_oauth.py` | `core/gmail/gmail_workspace_oauth.py` | 57 | 8 | **7** | 1 | **A / E** | **B** | **Keep both** — IMAP ingest OAuth |
| `contacto_gmail_source.py` | `core/gmail/contacto_gmail_source.py` | 93 | 8 | **34** | 1 | **A / E** | **B** | **Keep both** — canonical Gmail predicate; API mirror |

**Tests:** `test_gmail_send_inline_images.py`, `test_contacto_gmail_source_contract.py`, `test_core_import_surface.py`.

---

## Duplicate pairs — mart

| Root module | Core shim | Root LOC | Core LOC | Root import files | Core import files | Root class | Core class | Phase 5 |
|-------------|-----------|----------|----------|-------------------|-------------------|------------|------------|---------|
| `business_mart.py` | `core/mart/business_mart.py` | 261 | 8 | **68** | 3 | **A / E** | **B** | **Keep both** — `emails_in`, `domain_of`, mart helpers |
| `business_mart_schema.py` | `core/mart/business_mart_schema.py` | 103 | 8 | **7** | 1 | **A / E** | **B** | **Keep both** — DDL bundled into `db.init_schema` |

**Note:** Mart **build** logic is partially extracted to `core/mart/build_runner.py` (and builders), which **imports root** `business_mart` helpers — not a duplicate pair.

**Tests:** `test_build_business_mart.py`, `test_build_business_mart_phase2.py`, `test_business_mart_internal_domains.py`, Streamlit browse tests, `test_core_import_surface.py`.

---

## Duplicate pairs — outbound (policy-critical)

| Root module | Core shim | Root LOC | Core LOC | Root import files | Core import files | Root class | Core class | Phase 5 |
|-------------|-----------|----------|----------|-------------------|-------------------|------------|------------|---------|
| `candidate_export_gate.py` | `core/outbound/candidate_export_gate.py` | 129 | 10 | **36** | 1 | **A / E** | **B** | **Keep both** — single export eligibility policy |
| `outbound_core.py` | `core/outbound/outbound_core.py` | 131 | 8 | **31** | 0 | **A / E** | **B** | **Keep both** — Sent folders, sender, run envelope |
| `next_marketing_queue.py` | `core/outbound/next_marketing_queue.py` | 228 | 8 | **7** | 0 | **A / E** | **B** | **Keep both** |
| `outreach_contact_state.py` | `core/outbound/outreach_contact_state.py` | 255 | 8 | **19** | 0 | **A / E** | **B** | **Keep both** — sidecar memory |
| `marketing_export_context.py` | `core/outbound/marketing_export_context.py` | (root) | 8 | **24** | 0 | **A / E** | **B** | **Keep both** |
| `marketing_contact_noise.py` | `core/outbound/marketing_contact_noise.py` | (root) | 8 | **6** | 0 | **A / E** | **B** | **Keep both** |
| `marketing_supplier_domains.py` | `core/outbound/marketing_supplier_domains.py` | (root) | 8 | **13** | 0 | **A / E** | **B** | **Keep both** |
| `contact_email_suppression.py` | `core/outbound/contact_email_suppression.py` | (root) | 8 | **23** | 0 | **A / E** | **B** | **Keep both** |
| `contact_domain_suppression.py` | `core/outbound/contact_domain_suppression.py` | (root) | 8 | **11** | 0 | **A / E** | **B** | **Keep both** |
| `csv_contracts.py` | `core/outbound/csv_contracts.py` | (root) | 8 | **6** | 0 | **A / E** | **B** | **Keep both** |
| `outbound_sent_preflight.py` | `core/outbound/outbound_sent_preflight.py` | (root) | 8 | **7** | 0 | **A / E** | **B** | **Keep both** |
| `merge_marketing_contact_csvs.py` | `core/outbound/merge_marketing_contact_csvs.py` | 156 | 8 | **3** | 0 | **A** | **B** | **Keep both** |
| `manual_html_outreach_batch.py` | `core/outbound/manual_html_outreach_batch.py` | (root) | 8 | **3** | 0 | **A** | **B** | **Keep both** |

**Core-only outbound (already extracted — not root duplicates):**

| Module | Core import files | Class | Notes |
|--------|-------------------|-------|-------|
| `core/outbound/broad_marketing_contacts.py` | **5** | **A in core** | Stage 6C1; script remains entrypoint |
| `core/outbound/do_not_repeat_master.py` | **4** | **A in core** | Stage 6C2; imports `core.mart.business_mart.emails_in` |

**Tests:** `test_outbound_core.py`, `test_outbound_sent_preflight.py`, `test_next_marketing_queue_outbound_integration.py`, `test_archive_lane_outbound_integration.py`, gate/campaign tests (`test_cyber_outreach_campaign.py`, `test_presentacion_*`, `test_audit_contacted_universe.py`), `test_broad_marketing_contacts_core.py`, `test_do_not_repeat_master_core.py`, `test_core_import_surface.py`.

---

## Duplicate pairs — suppliers

| Root module | Core shim | Root LOC | Core LOC | Root import files | Core import files | Root class | Core class | Phase 5 |
|-------------|-----------|----------|----------|-------------------|-------------------|------------|------------|---------|
| `supplier_schema.py` | `core/suppliers/supplier_schema.py` | 109 | 8 | **8** | 1 | **A** | **B** | **Keep both** |
| `supplier_workbook.py` | `core/suppliers/supplier_workbook.py` | 851 | 8 | **5** | 1 | **A** | **B** | **Keep both** |

**Tests:** `test_supplier_schema.py`, `test_supplier_workbook.py`, `test_streamlit_suppliers_browse.py`, `test_core_import_surface.py`.

---

## Duplicate pairs — leads (`lead_*` / `leads_*`)

All **17** lead library modules follow the same pattern: **root = A**, **`core/leads/<same_name>.py` = B** (~8 LOC shim).

| Root module | Root LOC | Root import files | Core import files | Safety |
|-------------|----------|-------------------|-------------------|--------|
| `leads_schema.py` | 303 | **46** | 1 | **E** — DDL + migrations |
| `leads_ingest.py` | 41 | **10** | 0 | **E** |
| `leads_match.py` | 230 | **3** | 0 | **E** |
| `leads_normalize.py` | 273 | **3** | 0 | **E** |
| `leads_enrich.py` | 248 | **4** | 0 | **E** |
| `leads_score.py` | 151 | **3** | 0 | **E** |
| `leads_equipment.py` | 73 | **3** | 0 | **E** |
| `lead_accounts_schema.py` | 147 | **5** | 0 | **E** |
| `lead_contact_research.py` | 218 | **4** | 0 | **E** — precision import path |
| `lead_export_queries.py` | 66 | **17** | 0 | **E** |
| `lead_identity_norm.py` | 43 | **3** | 0 | **E** |
| `lead_master_audit.py` | 376 | **4** | 0 | **E** |
| `lead_master_dedupe.py` | 192 | **3** | 0 | **E** |
| `lead_master_keys.py` | 115 | **8** | 0 | **E** |
| `lead_normalize_upsert.py` | 88 | **4** | 0 | **E** |
| `lead_provenance.py` | 179 | **6** | 0 | **E** |
| `lead_upstream_reconcile.py` | 226 | **11** | 0 | **E** |

**Tests:** `test_leads_*.py`, `test_lead_*.py`, `test_import_lead_contact_research_csv.py`, `test_lead_account_script_entrypoints.py`, `test_core_import_surface.py`.

---

## Related shim pattern — `commercial_intel_*` (root → `commercial/`)

Not part of `core/*`, but same **compatibility** question:

| Root shim | Canonical package | Root class | Import notes |
|-----------|-------------------|------------|--------------|
| `commercial_intel_schema.py` | `commercial/commercial_intel_schema.py` | **B** | Used from `sqlite_migrate.py`, commercial scripts |
| `commercial_intel_queries.py` | `commercial/commercial_intel_queries.py` | **B** | |
| `commercial_intel_rules.py` | `commercial/commercial_intel_rules.py` | **B** | |
| `commercial_intel_review.py` | `commercial/commercial_intel_review.py` | **B** | |

**Fan-in:** ~**12** files reference `commercial.commercial_intel_*` or root shims; `test_commercial_intel_package_layout.py` locks layout.

**Phase 5 candidate strength:** **Weak.** Could become **D** after a dedicated import sweep (similar to operational_trust root shim removal documented in `PACKAGE_DOMAINS.md`), but **not** grouped with root/core pairs.

---

## Safe removal candidates (Phase 5)

| Candidate | Verdict | Evidence |
|-----------|---------|----------|
| Any **root** module in tables above | **Not D** | Implementation + high fan-in; removal breaks scripts, Streamlit, API |
| Any **`core/*` re-export shim** | **Not D** | Documented import surface; `test_core_import_surface.py` |
| **`commercial_intel_*` root shims** | **Weak D** (later) | Low fan-in; canonical code in `commercial/` |
| Tracked **`__pycache__`** | **N/A** | None tracked in git |

**Strong Phase 5 grouped removals from this audit:** **None.** Phase 5A–5G correctly targeted **deprecated scripts and Streamlit-named shims**, not the intentional Stage 2A/2B root↔core layout.

---

## Unsafe / not-yet candidates

| Asset | Why **E** / defer |
|-------|-------------------|
| `candidate_export_gate.py` | Single export policy; 36+ import sites; Streamlit + all campaign CLIs |
| `outbound_core.py` | Sent-folder truth; `apps/api` operator repo |
| `outreach_contact_state.py` | Post-send sidecar; suppression adjacency |
| `db.py` / `sqlite_migrate.py` | All ingest + mart + migrate paths |
| `config.py` | Every script entrypoint |
| `contacto_gmail_source.py` | Operational scope predicate; Postgres mirror |
| `business_mart.py` | `emails_in` / `domain_of` used across QA, campaigns, core mart builders |
| All **`lead_*` / `leads_*` root modules** | Lead pipeline + precision import contract |
| Physical **move root → core** (invert shim direction) | Requires Stage 6C vertical PR + full test matrix per domain |

---

## Tests required before any future removal or physical move

Run **domain-specific** suites plus import smoke:

```bash
cd apps/email-pipeline

# Always
uv run pytest tests/test_core_import_surface.py tests/test_package_import_boundaries.py -q

# Infrastructure
uv run pytest tests/test_sqlite_migrate.py tests/test_build_business_mart.py tests/test_build_business_mart_phase2.py -q

# Gmail
uv run pytest tests/test_contacto_gmail_source_contract.py tests/test_gmail_send_inline_images.py tests/test_workspace_gmail_imap_ingest.py -q

# Outbound / gate
uv run pytest tests/test_outbound_core.py tests/test_outbound_sent_preflight.py \
  tests/test_next_marketing_queue_outbound_integration.py tests/test_broad_marketing_contacts_core.py \
  tests/test_do_not_repeat_master_core.py -q

# Leads
uv run pytest tests/test_leads_match.py tests/test_leads_normalize.py tests/test_lead_contact_research.py \
  tests/test_import_lead_contact_research_csv.py -q

# API cross-app (from apps/api)
uv run pytest tests/mirror/ -q
```

After import-path migration, add **shim parity tests** (pattern used in Phase 5E–5G Streamlit retirements): assert removed path absent, canonical path present, behavior unchanged.

---

## Suggested PR sequence (Stage 6C+, not Phase 5)

Migrate **one vertical at a time**; **do not** delete root and core in the same PR until all call sites use the new canonical path.

| Order | Vertical | First actions | Risk |
|-------|----------|---------------|------|
| **1** | **Docs-only** | Mark root vs core truth in `PACKAGE_DOMAINS.md`; require `core.*` in **new** code only | Low |
| **2** | **Infrastructure** | Optional: new scripts use `core.config`, `core.db`, `core.sqlite_migrate`; keep root shims | Low |
| **3** | **Gmail** | Migrate `contacto_gmail_source` / OAuth imports in API + mirror tests | Medium |
| **4** | **Mart** | Continue `build_business_mart.py` thinning; root `business_mart` last | Medium |
| **5** | **Suppliers** | Low fan-in; good pilot for physical move | Low |
| **6** | **Leads** | One submodule per PR (`leads_schema` first) | Medium |
| **7** | **Commercial intel root shims** | Point `sqlite_migrate` + scripts at `commercial.*`; remove 4 root shims | Low |
| **8** | **Outbound / gate** | **Last** — `candidate_export_gate`, `outbound_core`, suppressions | **High** |

Each vertical PR should include: grep evidence (`rg 'origenlab_email_pipeline\.<old>'`), updated live docs (`README.md`, `SCRIPT_MAP.md` if entrypoints touched), and the test commands above.

---

## Reference counting methodology

Counts generated 2026-06-02 by scanning **`apps/email-pipeline/**`** and **`apps/api/**`** for `*.py`, `*.md`, `*.sh`:

- **Root import files:** unique files matching `origenlab_email_pipeline.<module>\b`
- **Core import files:** unique files matching `origenlab_email_pipeline.core.<path>\b`

Shim files themselves count as 1 core reference when they import root. **`test_core_import_surface.py`** accounts for most core-only hits on infrastructure/gmail/mart/supplier shims.

---

## Appendix — example `rg` commands (repeat audit)

```bash
cd apps/email-pipeline

# Pair existence
rg -l 'streamlit_canonical_dashboard_sql'  # should stay empty post-5G
rg -l 'origenlab_email_pipeline\.db\b'
rg -l 'origenlab_email_pipeline\.core\.db\b'

# High fan-in modules
rg -c 'origenlab_email_pipeline\.config\b' --glob '*.py' | sort -t: -k2 -nr | head

# API dependency
rg 'origenlab_email_pipeline\.(config|db|outbound_core|business_mart|contacto_gmail_source)\b' ../api

# Tracked cache
git ls-files '*__pycache__*'
```

---

## Handoff

| Item | Result |
|------|--------|
| **Files changed** | `docs/audits/ROOT_CORE_COMPATIBILITY_AUDIT_20260602.md` (this report only) |
| **Code/tests changed** | None (audit-only) |
| **Phase 5 removals recommended** | **None** from root/core pairs |
| **Next safe simplification** | Continue Phase 5 script/Streamlit track; defer root/core physical migration to Stage 6C+ |
