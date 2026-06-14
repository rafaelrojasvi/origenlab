# Email pipeline code quality snapshot — 2026-06-14

**Status:** read-only audit / planning guidance only  
**Scope:** `apps/email-pipeline` — documentation snapshot from local planner runs  
**Authority:** **Not** deletion or move authority. Low import counts, zero doc references, and planner heuristics do **not** prove a file is unused.

This document summarizes today’s planner outputs for humans and agents planning small, safe follow-up PRs. It does **not** authorize refactors, deletions, or runtime changes.

See also: [`../architecture/CRITICAL_SURFACE_INDEX.md`](../architecture/CRITICAL_SURFACE_INDEX.md) · [`REDUCTION_SHORTLIST_20260607.md`](REDUCTION_SHORTLIST_20260607.md) · [`../CRUD_SAFETY.md`](../CRUD_SAFETY.md) · [`../SCRIPT_MAP.md`](../SCRIPT_MAP.md)

---

## Recent cleanup context

The following merged PRs established the planner and doc guardrails this snapshot builds on:

| PR | Topic |
|----|-------|
| **#216** | Dependency group docs — clarifies optional vs core package boundaries |
| **#217** | Source-quality planner generated-report exclusions — keeps planner scans focused on live code |
| **#218** | Critical surface index — ownership map for high-risk paths ([`CRITICAL_SURFACE_INDEX.md`](../architecture/CRITICAL_SURFACE_INDEX.md)) |
| **#219** | Import planner zero-reference review lists — surfaces candidates for manual review, not auto-delete |
| **#220** | Parseable import planner JSON stdout — machine-readable output for audits and CI |
| **#221** | Dashboard dependency bump — verified separately in `apps/dashboard`; no email-pipeline runtime change |

---

## Planner snapshot (2026-06-14)

Local runs from `apps/email-pipeline/` (outputs under `reports/local/` — **gitignored, do not commit**):

| Metric | Count |
|--------|------:|
| `src/` Python files | 299 |
| `scripts/` Python files | 186 |
| **Total Python files** | **485** |
| Total functions | 2945 |
| Public functions | 1808 |
| Classes | 235 |
| Break-glass scripts | 26 |
| Zero Python-import non-facade modules | 12 |
| Zero doc/test reference scripts | 5 |
| Dangerous scripts flagged by import planner | 15 |

**Commands used:**

```bash
cd apps/email-pipeline
uv run python scripts/qa/plan_source_quality.py --top 40
uv run python scripts/qa/plan_function_surface.py
uv run python scripts/qa/plan_import_surface.py
uv run python scripts/qa/plan_script_consolidation.py
```

Re-run after major tree changes; compare summaries — CSV/JSON outputs are **heuristic snapshots**, not live inventory authority.

---

## Biggest code areas (by LOC bucket)

| Area | Files | LOC | Notes |
|------|------:|----:|-------|
| `lead_research` | 64 | 17,574 | Largest vertical; mixed operator and lab surfaces |
| `qa_reports` | 51 | 12,871 | QA/export/reporting sprawl |
| `postgres_mirror` | 46 | 11,793 | Mirror sync and loaders — high side-effect risk |
| `outbound_safety` | 52 | 8,588 | DNR, suppression, send gates |
| `tatiana_lab` | 40 | 8,004 | Parked/lab boundary — see [`../EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md) |
| `commercial_intel` | 28 | 7,847 | Deal/promotion logic |
| `warm_cases` | 8 | 2,871 | **High-risk / unknown-review** — characterize before any split |

### `warm_cases` — characterize-then-split-later

Only eight files but concentrated complexity and operator-facing rules. **Recommended posture:** add characterization tests and document behavior **before** any file split or reduction PR. Do not treat low file count as low risk.

---

## Top large files (single-file LOC)

| File | LOC | Bucket |
|------|----:|--------|
| `src/.../core/research_automation.py` | 1683 | lead_research |
| `src/.../commercial/commercial_deal_promotion.py` | 1627 | commercial_intel |
| `src/.../leads/contacted_universe_audit.py` | 1239 | lead_research |
| `scripts/migrate/mart_core_postgres_migrate.py` | 1181 | postgres_mirror |
| `scripts/sync/dashboard_postgres_sync.py` | 1179 | postgres_mirror |
| `src/.../warm_cases/warm_case_sender_rules.py` | 1047 | warm_cases |

Large LOC alone is not a deletion signal — many of these sit on critical or break-glass paths.

---

## Do not touch casually

These surfaces require explicit operator intent, dry-run first, and review against [`CRITICAL_SURFACE_INDEX.md`](../architecture/CRITICAL_SURFACE_INDEX.md):

- **Send / purge scripts** — Gmail API send, SQLite purge, archive destructive paths
- **Gmail ingest** — canonical Sent/inbox truth (`05_workspace_gmail_imap_to_sqlite.py` and chain)
- **Postgres mirror / migrations** — mirror load, alembic, TRUNCATE/DELETE risk
- **Outbound apply / suppression paths** — NDR apply, DNR export, anti-repeat refresh with `--apply`
- **Break-glass scripts** — 26 flagged; default to plan-only unless operator orders apply

SQLite remains **operational truth** for outbound safety. Postgres mirror and dashboard reads are **reporting**, not send approval.

---

## Recommended next PRs (planning only)

1. **Characterization tests for `warm_case_sender_rules.py`** — lock observable behavior before any split or refactor.
2. **Dashboard test `act()` warnings** — clean separately in `apps/dashboard`; out of scope for email-pipeline runtime.
3. **Tatiana / lab optional dependency boundary** — document or park in [`../EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md) / dedicated boundary doc; no silent coupling into daily-core.
4. **Zero-reference files** — do **not** delete without owner review, repo-wide grep/search, contract tests, and manual confirmation. Import planner lists are review queues, not delete lists.

---

## Validation (docs PR)

When validating this document only:

```bash
cd apps/email-pipeline
uv run python scripts/qa/plan_source_quality.py --top 10
cd ../..
./scripts/security/check-public-repo-hygiene.sh
git diff --stat
git diff -- apps/email-pipeline/docs/audits/CODE_QUALITY_SNAPSHOT_20260614.md
```

Do **not** run `--apply`, send, purge, NDR apply, Postgres migrate/mirror apply, or daily-core apply as part of this doc PR.
