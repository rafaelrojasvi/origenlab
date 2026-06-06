# Daily core workflow (canonical)

Status: canonical (operator contract)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-05

Related: [`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md) · [`RUNBOOK.md`](../RUNBOOK.md) · [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md) · post-send: [`POST_SEND_SAFE_LOOP.md`](POST_SEND_SAFE_LOOP.md)

This document defines the **daily operating layer** for `apps/email-pipeline`: what operators run to refresh SQLite operational truth and safety exports **without** sending mail, purging data, or requiring Postgres.

---

## Canonical daily command

From `apps/email-pipeline/`:

```bash
uv run origenlab refresh-dashboard --apply --no-mirror
```

This is the **current daily core** command: it runs the seven steps below against **SQLite** and writes **reports** under `reports/out/`. It **does not** run Postgres mirror sync.

---

## Plan-only (safe default)

Inspect the workflow before any writes:

```bash
uv run origenlab refresh-dashboard
```

Plan-only mode prints the step list and exits **without** Gmail ingest, mart rebuild, commercial intel refresh, or other mutating steps.

---

## Daily core steps (in order)

When `--apply --no-mirror` is used, the orchestrator runs:

| # | Step | CLI subcommand | Notes |
|---|------|----------------|-------|
| 1 | Gmail ingest | `gmail-ingest` | INBOX + Sent (`[Gmail]/Enviados`); updates SQLite `emails` |
| 2 | Business mart rebuild | `build-mart -- --rebuild` | Break-glass: deletes and rebuilds mart tables |
| 3 | Commercial intel | `build-commercial-intel` | Incremental refresh of SQLite `commercial_*` |
| 4 | Outbound safety exports | `refresh-safety` | Anti-repeat / DNR export chain to `reports/out` |
| 5 | NDR review batches | `ndr-review` | **Read-only** NDR review queue — **does not apply suppressions** |
| 6 | Post-send digest | `post-send-digest` | Report artifacts after contacted-universe audit inputs |
| 7 | Operator status | `status` | READY / CAUTION / BLOCKED snapshot |

Optional flags (same contract, different shape): `--skip-ingest`, `--since-days N` — see `uv run origenlab refresh-dashboard --help`.

---

## Operational truth contract

| Topic | Source of truth |
|-------|-----------------|
| Ingested mail + Sent history | **SQLite** (`emails`), populated by Gmail ingest (Sent folder in SQLite) |
| Anti-repeat / contacted memory | **SQLite** + safety exports from `refresh-safety` |
| Send / already-contacted decisions | **SQLite + Gmail Sent history inside SQLite** — not Postgres, not dashboard UI |

**Postgres mirror** and **deployed dashboard / API status** are **read-only visibility** for reporting and operator UI. They are **not send approval**. LISTO / READY on a dashboard does **not** mean an outbound batch may be sent.

---

## Daily core safety boundaries

The daily core workflow (`refresh-dashboard --apply --no-mirror`):

- **Does not send emails.**
- **Does not purge data.**
- **Does not apply NDR suppressions** (`ndr-review` builds review batches only).
- **Does not run Alembic.**
- **Does not require Postgres** (`--no-mirror` skips mirror sync).
- **Does not approve outbound sends** — use separate campaign / export / send procedures after readiness checks.

Mart rebuild (`build-mart --rebuild`) **does** mutate SQLite mart tables. That is expected for daily core; it is not Gmail send and not Postgres mirror.

---

## Optional mirror (separate step)

Postgres reporting visibility is **outside** daily core when using `--no-mirror`. Run mirror only when a Postgres URL is configured and reporting visibility is needed:

```bash
uv run origenlab mirror-dashboard --apply
```

Requires `ORIGENLAB_POSTGRES_URL`, `ALEMBIC_DATABASE_URL`, or `ORIGENLAB_CLOUD_POSTGRES_URL`. Default `mirror-dashboard` (no `--apply`) is dry-run. Schema migrations (`alembic upgrade head`) are **not** part of daily core — use `mirror-dashboard --alembic --apply` only with explicit ops approval.

**Do not** treat mirror success as permission to send.

---

## What daily core is not

- **Not** the full post-send loop — see [`POST_SEND_SAFE_LOOP.md`](POST_SEND_SAFE_LOOP.md) after sends.
- **Not** outbound campaign export or send — see [`RUNBOOK.md`](../RUNBOOK.md) daily outbound sections.
- **Not** a substitute for `check-readiness` before building send batches.
- **Not** institution grouping or cleanup planners — see `plan_function_surface.py` / `plan_import_surface.py` (read-only audits).

---

## Quick reference

```bash
cd apps/email-pipeline

# Plan only — no mutations
uv run origenlab refresh-dashboard

# Daily core — SQLite + reports, no Postgres mirror
uv run origenlab refresh-dashboard --apply --no-mirror

# Optional mirror (separate; Postgres required)
uv run origenlab mirror-dashboard --apply
```
