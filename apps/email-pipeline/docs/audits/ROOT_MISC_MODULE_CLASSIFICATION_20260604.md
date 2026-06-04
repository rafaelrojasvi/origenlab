# Root misc module classification — 2026-06-04

Status: read-only audit (docs only)  
Branch context: `main`  
Source: deep structure audit (`reports/local/deep-structure-audit/`) — **this doc does not embed generated CSVs**

## 1. Summary

The deep-structure audit bucketed **16** package-root modules as `root_misc_unknown`. Manual inspection (git-tracked sources, `rg`, AST docstrings, `uv run origenlab audit-facades`) shows **none are accidental orphans** and **none are safe to delete** from fan-in alone.

| Outcome | Count | Modules |
|---------|------:|---------|
| **Stable entrypoint** | 1 | `cli.py` |
| **Facade-pair root implementation** | 4 | `contacto_gmail_source`, `gmail_workspace_oauth`, `marketing_supplier_domains`, `supplier_schema` |
| **Keep root implementation** | 6 | `cases_review_queue`, `operational_scope`, `freshness_dates`, `reported_non_delivery_signals`, `contact_export_queries`, `timeutil` |
| **Schema / SQL support** | 1 | `pipeline_meta_schema` |
| **Shared utility (script-backed)** | 3 | `pipeline_run_recorder`, `hunt_csv_alignment`, `dr50_payload_loader` |
| **Script / manual tool library** | 1 | `export_jsonl` |

**Cross-cutting rules encoded here:**

- Do **not** delete any module based only on low package fan-in; several are **script entry libraries** or **monorepo API surfaces** (`apps/api` imports `cases_review_queue`, `operational_scope`).
- `cli.py` is the **`origenlab` pyproject entrypoint** — not unknown misc code.
- Four modules are **facade-pair roots**; confirm with `uv run origenlab audit-facades` before any import migration.
- Modules touching **Gmail**, **send/outreach**, **Postgres mirror**, or **SQLite mutation** (`INSERT`/`commit`) are **freeze / audit-first** for logic changes — docs and read-only tests are still safe.
- Future work should be **small PRs**: docs → characterization tests → read-only operator CLI wrappers → core facades only when needed → moves only after import graph + tests.

**Facade pairs (audit-facades, 2026-06-04):**

| Root | Core facade |
|------|-------------|
| `contacto_gmail_source.py` | `core/gmail/contacto_gmail_source.py` |
| `gmail_workspace_oauth.py` | `core/gmail/gmail_workspace_oauth.py` |
| `marketing_supplier_domains.py` | `core/outbound/marketing_supplier_domains.py` |
| `supplier_schema.py` | `core/suppliers/supplier_schema.py` |

---

## 2. Decision table (all 16 modules)

Fan-in = count of **other** `src/origenlab_email_pipeline/**/*.py` files importing `origenlab_email_pipeline.<module>` (root path). Script/docs counts are **files** under `apps/email-pipeline` referencing the stem. Monorepo **`apps/api`** imports noted where relevant.

| Module | LOC | Primary classification | Docstring (first line) | Fan-in | Tests | Scripts | Docs | Main | Argparse | File write | Risk terms | Responsibility | Safe first action | Do-not-touch |
|--------|----:|------------------------|-------------------------|-------:|------:|--------:|-----:|:----:|:--------:|:----------:|--------------|----------------|-----------------|--------------|
| `cases_review_queue.py` | 275 | **keep_root_implementation** | Message-level review queue for Streamlit «Casos para revisar» (v1: Gmail contacto only). | 5 | 3+ | 2 | 3 | no | no | no | gmail | Read-only SQL queue for Streamlit + **`apps/api`** warm/case list endpoints. | Link from `PACKAGE_DOMAINS.md`; extend API contract tests. | Do not add send/draft here; see `docs/pipeline/CASOS_PARA_REVISAR.md`. |
| `cli.py` | 67 | **stable_entrypoint** | Unified operator CLI — thin entrypoint (Phase 8B). | 0 | 9+ | 34+ | 47+ | yes | no | no | gmail, postgres (re-exports) | `pyproject.toml` → `origenlab_email_pipeline.cli:main`; delegates to `operator_cli`. | Document as canonical CLI surface in operator handoff. | **Not unknown.** Do not fold into a subpackage without migration plan. |
| `contact_export_queries.py` | 61 | **schema_or_sql_support** | Shared SQL for ``contact_master`` cold-export / audit candidate selection. | 0* | 1 | 2 | 1 | no | no | no | — | Shared `WHERE`/`ORDER BY` for marketing export + candidate audit scripts. | Add `SCRIPT_MAP.md` cross-refs to `export_marketing_from_contact_master` / `export_candidate_audit`. | Keep SQL aligned across export vs audit (module comment contract). |
| `contacto_gmail_source.py` | 93 | **facade_pair_root_implementation** | Canonical SQL and source-tier classification for contacto@origenlab.cl Gmail Workspace ingest. | 17 | 8+ | 3 | 4 | no | no | no | gmail | **Operational truth** for `emails.source_file` tier + SQL predicates. | Prefer **new** imports via `core.gmail.contacto_gmail_source`; add regression test if predicates change. | **Freeze/audit-first** — wrong predicate breaks Streamlit, outbound readiness, NDR, API scope. |
| `dr50_payload_loader.py` | 67 | **script_or_manual_tool** | Load versioned **DR50** (deep-research) contact JSON with SHA256 verification. | 0* | 1 | 1 | 1 | no | no | no | — | Verified loader for `scripts/leads/campaigns/data/` payloads. | Document in `scripts/leads/README.md` / campaign runbooks. | Not daily ops; do not wire to `refresh-dashboard` without review. |
| `export_jsonl.py` | 101 | **script_or_manual_tool** | Stream emails table to JSONL (UTF-8). | 0* | 0 | 1 | 1+ | no | no | yes (JSONL) | — | Library for `scripts/ingest/03_sqlite_to_jsonl.py` (ML/Tatiana path). | Mark **non-daily** in ingest docs (already in `ARCHITECTURE.md`). | Large export I/O; not operator-dashboard path. |
| `freshness_dates.py` | 79 | **shared_utility** | Plausible-date policy for **derived** mart and freshness (raw archive unchanged). | 3 | 2 | 0 | 2 | no | no | no | — | Mart timeline date filtering (`email_date_iso_for_mart_timeline`). | Keep tests for slack-day edge cases (`test_freshness_dates.py`). | Changing rules affects mart bounds globally. |
| `gmail_workspace_oauth.py` | 57 | **facade_pair_root_implementation** | Google Workspace / Gmail IMAP OAuth2 helpers (optional dependency group `gmail` or `workspace`). | 0* | 4+ | 2 | 4 | no | no | yes (token JSON) | gmail | OAuth/XOAUTH2 for **read ingest** + break-glass send script. | Document token paths; never add to daily `origenlab` without explicit approval. | **Freeze/audit-first** — Gmail credentials; `send_inline_html_email_via_gmail_api.py` imports root. |
| `hunt_csv_alignment.py` | 57 | **shared_utility** | Contact-hunt CSV ``id_lead`` set alignment (current vs merged exports). | 0* | 1 | 4 | 1 | no | no | no | — | CSV cohort parity checks for hunt merge / operational trust QA. | Add one-line pointer in `scripts/leads/advanced/` README. | Used by trust audits; changing semantics affects lead QA. |
| `marketing_supplier_domains.py` | 38 | **facade_pair_root_implementation** | Domains to exclude from cold outreach: known suppliers (proveedores). | 10† | 1 | 0 | 2 | no | no | no | send/outreach | `supplier_master.domain_norm` → outreach blocklist. | Import via `core.outbound.marketing_supplier_domains` for new code. | **Freeze/audit-first** for outreach safety semantics. |
| `operational_scope.py` | 156 | **keep_root_implementation** | Operational (canonical Gmail) vs archive (full mart) scope for dashboards and API. | 6 | 1+ | 0 | 0‡ | no | no | no | gmail, postgres, send | `DataScope` canonical/archive; Postgres relation names; noise blocklists. | Add docs row in `PACKAGE_DOMAINS.md`; **`apps/api`** mirror tests already import. | **Freeze/audit-first** — API + Streamlit + mirror SQL depend on scope helpers. |
| `pipeline_meta_schema.py` | 31 | **schema_or_sql_support** | Pipeline run audit and key/value metadata tables (additive, shared SQLite file). | 5 | 1+ | 0 | 3 | no | no | no | sqlite_write | DDL for `pipeline_run` / `pipeline_kv`. | Keep paired with `db.py` / `sqlite_migrate` docs. | Schema migrations need dedicated PR + migrate tests. |
| `pipeline_run_recorder.py` | 83 | **shared_utility** | Record pipeline runs and pipeline_kv entries for reproducibility. | 3 | 1+ | 4 | 2 | no | no | no§ | sqlite_write | `start_run` / `finish_run` / `set_kv` used by mart & commercial scripts. | Characterization tests on recorder (partial via mart tests). | Mutates SQLite when scripts run — not for read-only operator snapshots. |
| `reported_non_delivery_signals.py` | 41 | **keep_root_implementation** | Heuristics: recipient text suggests they never got our outreach (inactive / mailbox issue). | 1 | 3 | 0 | 1 | no | no | no | gmail, send | Pure text heuristics; consumed by `reported_non_delivery_contacto_scan.py`. | Keep parity tests (`test_ndr_tool_parity.py`). | Conservative patterns by design; do not loosen without NDR review. |
| `supplier_schema.py` | 109 | **facade_pair_root_implementation** | Supplier / sourcing layer (SQLite DDL). Separate from buyer ``lead_master``. | 2 | 4+ | 1 | 5 | no | no | no¶ | sqlite_write | Supplier tables DDL + ensure helpers. | Import via `core.suppliers.supplier_schema` for new code. | **Freeze/audit-first** for DDL changes (workbook import chain). |
| `timeutil.py` | 10 | **shared_utility** | Shared UTC timestamps for pipeline rows and metadata (single format). | 18 | 3+ | 4 | 1 | no | no | no | — | `now_iso()` for pipeline/mart metadata. | No move needed; highest fan-in utility. | Trivial but widely imported — changing format breaks audits. |

\* Fan-in **0** at root path but **script- or test-imported** directly (expected for SQL helpers, OAuth, export library).  
† Fan-in **10** includes imports of `core.outbound.marketing_supplier_domains` (re-export).  
‡ Listed in `PACKAGE_DOMAINS.md` table but not grep-heavy in `docs/` filenames.  
§ Writes via SQLite `commit`, not filesystem.  
¶ `ensure_*` commits when called from migration/import paths.

### Secondary tags (future PR hints)

| Module | Also applies |
|--------|----------------|
| `cases_review_queue.py` | **move_candidate_later** → `read/` when `apps/api` case endpoints stabilize |
| `operational_scope.py` | **move_candidate_later** → `read/` per Streamlit retirement / API scope work |
| `contact_export_queries.py` | **possible_core_facade_candidate_later** (low priority; small SQL module) |
| `export_jsonl.py` | **possible_operator_cli_mapping_later** — only if ML export gets a read-only wrapper (low value) |
| `dr50_payload_loader.py`, `hunt_csv_alignment.py` | **possible_operator_cli_mapping_later** — only for lab/QA wrappers, not daily ops |
| `gmail_workspace_oauth.py` | **freeze_audit_first** — never daily CLI without explicit approval |
| Facade quartet | **possible_core_facade_candidate_later** — facades **exist**; work is **import migration**, not new shims |

---

## 3. Safe low-risk candidates

Work safe **without** runtime refactors (docs / tests / read-only tooling only):

| Module | Why low risk | Suggested PR |
|--------|--------------|--------------|
| `timeutil.py` | Tiny, pure, heavy fan-in | Contract test already (`test_timeutil_contract.py`); doc one-liner in `PACKAGE_DOMAINS.md` |
| `freshness_dates.py` | Pure date policy, tested | Extend edge-case tests only |
| `contact_export_queries.py` | SQL-only, script contract | Doc + lock column order in existing tests |
| `hunt_csv_alignment.py` | CSV QA, no DB writes | Script README + trust-audit cross-link |
| `dr50_payload_loader.py` | File-read + SHA256 | Campaign doc note |
| `pipeline_meta_schema.py` | DDL only | Cross-link in `SCHEMA_OWNERSHIP.md` |
| `cli.py` | Stable entrypoint | Operator handoff: “not misc unknown” |
| Facade roots (4) | Shims exist | Doc: “import `core.*` for new code” (no file moves) |

---

## 4. Needs audit / freeze candidates

Logic or schema changes require explicit review (Gmail, outreach, Postgres, SQLite mutation):

| Module | Freeze reason | Read-only safe work |
|--------|---------------|---------------------|
| `contacto_gmail_source.py` | Canonical mailbox predicate | Doc + predicate regression tests |
| `gmail_workspace_oauth.py` | Gmail OAuth + token writes | Dependency smoke tests only |
| `marketing_supplier_domains.py` | Outreach suppression | Export audit tests |
| `operational_scope.py` | API + mirror + canonical/archive | `test_operational_scope.py`, API mirror tests |
| `cases_review_queue.py` | Gmail-scoped operator queue + API | Read-only fetch tests |
| `reported_non_delivery_signals.py` | NDR heuristics / false-positive risk | Parity tests |
| `supplier_schema.py` | Supplier DDL + imports | Schema tests |
| `pipeline_run_recorder.py` | Writes `pipeline_run` / `pipeline_kv` | Dry-run script tests |
| `export_jsonl.py` | Large data export side effect | Document non-daily; no CLI without approval |

---

## 5. Possible future package placement

**No moves in this audit.** Placement ideas for **later** named PRs only:

| Current root | Future home | Prerequisite |
|--------------|-------------|--------------|
| `cases_review_queue.py` | `read/cases_review.py` | `apps/api` import migration + Streamlit import update |
| `operational_scope.py` | `read/scope.py` | API + `postgres_dashboard_api` import analysis |
| `freshness_dates.py` | `core/mart/freshness_dates.py` | Mart builder import migration + facade if needed |
| `contact_export_queries.py` | `core/outbound/contact_export_queries.py` | Align with export scripts + facade |
| `hunt_csv_alignment.py` | `lead_research/` or `qa/` | Script import updates |
| `reported_non_delivery_signals.py` | `qa/` or stay root NDR cluster | Keep with `ndr_*` modules |
| `export_jsonl.py` | `ingest/` | `03_sqlite_to_jsonl.py` import change |
| Facade roots | **Stay root** | Implementations remain root per `MODULE_FACADE_AUDIT_20260604.md` |

---

## 6. Explicit non-goals

- **No** file deletes, moves, or import migrations in this audit.
- **No** new `origenlab` subcommands wrapping Gmail ingest, send, Postgres mirror, `--apply`, or `refresh-dashboard --apply`.
- **No** treating facade-pair roots as duplicate implementations to remove.
- **No** committing `reports/local/**` generated CSVs into git.
- **No** changing `warm_case_sender_rules.py`, outbound send paths, or Postgres migrate scripts under this doc-only PR.

---

## Verification (2026-06-04)

```bash
cd apps/email-pipeline
uv run origenlab audit-facades -- --fail-on-manual-review
uv run pytest tests/test_module_facade_audit.py tests/test_operator_cli.py -q
```

Expected: audit-facades exit 0; pytest **85 passed**.

```bash
cd "$(git rev-parse --show-toplevel)"
git diff --check
git status --short
```

Expected: clean after docs-only change (or only the new audit markdown staged).

---

## References

- [`MODULE_FACADE_AUDIT_20260604.md`](MODULE_FACADE_AUDIT_20260604.md)
- [`PACKAGE_DOMAINS.md`](../pipeline/PACKAGE_DOMAINS.md)
- [`CASOS_PARA_REVISAR.md`](../pipeline/CASOS_PARA_REVISAR.md)
- [`EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md)
- Operator CLI map: `src/origenlab_email_pipeline/operator_cli/constants.py`
