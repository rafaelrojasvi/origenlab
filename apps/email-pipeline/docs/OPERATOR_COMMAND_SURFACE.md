# Operator command surface

Status: canonical (navigation)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-03 (Phase 7C)

Procedures: [`RUNBOOK.md`](RUNBOOK.md) · post-send: [`pipeline/POST_SEND_SAFE_LOOP.md`](pipeline/POST_SEND_SAFE_LOOP.md) · tags / break-glass: [`SCRIPT_MAP.md`](SCRIPT_MAP.md).

## Operator CLI

```bash
cd apps/email-pipeline
uv run origenlab --help
uv run origenlab status
uv run origenlab daily-health
uv run origenlab refresh-safety
uv run origenlab validate-csvs
uv run origenlab check-readiness
uv run origenlab post-send-digest
uv run origenlab export-dnr
uv run origenlab ndr-review
uv run origenlab audit-overlap
uv run origenlab build-mart
uv run origenlab build-commercial-intel
uv run origenlab gmail-ingest
uv run origenlab gmail-ingest-folders
uv run origenlab mirror-dashboard
uv run origenlab mirror-dashboard --apply
uv run origenlab mirror-dashboard --alembic --apply
uv run origenlab refresh-dashboard
uv run origenlab refresh-dashboard --apply
uv run origenlab refresh-dashboard --apply --no-mirror
uv run origenlab refresh-dashboard --apply --mirror-dry-run
```

Module fallback: `uv run python -m origenlab_email_pipeline.cli <subcommand>`. Pass script flags after ``--`` where supported. **`gmail-ingest`** runs INBOX then `[Gmail]/Enviados` with `--skip-duplicate-message-id`; **rejects `--replace-source`**. **`mirror-dashboard`** defaults to sync `--dry-run`; **`--apply`** writes Postgres; **`--alembic --apply`** runs `alembic upgrade head` first. Requires **`ORIGENLAB_POSTGRES_URL`**, **`ALEMBIC_DATABASE_URL`**, or **`ORIGENLAB_CLOUD_POSTGRES_URL`**. **Advanced fallback** = `scripts/…` paths in the table below.

| CLI subcommand | Advanced fallback (`scripts/…`) | Notes |
|----------------|----------------------------------|--------|
| `status` | `qa/operator_status.py` | READY / CAUTION / BLOCKED |
| `daily-health` | `qa/run_daily_health_report.py` | Not a substitute for full post-send loop |
| `refresh-safety` | `qa/refresh_outbound_safety_memory.py` | Anti-repeat export chain |
| `validate-csvs` | `qa/validate_campaign_csvs.py` | CSV contracts |
| `check-readiness` | `qa/check_outbound_readiness.py` | Pre-send readiness |
| `post-send-digest` | `qa/build_post_send_digest.py` | After `audit_contacted_universe` |
| `export-dnr` | `qa/export_do_not_repeat_master.py` | Volume lane DNR |
| `ndr-review` | `qa/build_ndr_review_queue.py` | Read-only NDR batches |
| `audit-overlap` | `qa/export_contacted_lead_overlap_audit.py` | Pre-send overlap |
| `build-mart` | `mart/build_business_mart.py` | Break-glass; `--rebuild` deletes mart tables |
| `build-commercial-intel` | `commercial/build_commercial_intel_v1.py` | SQLite; incremental `commercial_*` refresh; `--rebuild` break-glass via passthrough |
| `gmail-ingest` | `ingest/05_workspace_gmail_imap_to_sqlite.py` (INBOX + Sent) | SQLite; daily refresh; rejects `--replace-source` |
| `gmail-ingest-folders` | same (`--list-folders`) | No; discover Sent label if `[Gmail]/Enviados` differs |
| `gmail-ingest-help` | same (`--help` only) | No; ingest flags reference |
| `mirror-dashboard` | `sync/sync_dashboard_postgres_mirror.py` | Postgres (dry-run default); `--apply` writes |
| `mirror-dashboard --alembic --apply` | alembic + sync script | Postgres; schema + mirror |
| `refresh-dashboard` | orchestrates CLI steps above | Plan only (default) |
| `refresh-dashboard --apply` | ingest → `build-mart --rebuild` → safety → digest → status → `mirror-dashboard --apply` | SQLite + reports + Postgres |
| `refresh-dashboard --apply --no-mirror` | same without mirror | SQLite + reports |
| `refresh-dashboard --apply --mirror-dry-run` | SQLite/report steps + `mirror-dashboard` dry-run | Mixed |

**Truth:** SQLite + Gmail Sent in `emails`. Postgres / dashboard LISTO ≠ send approval.

**Mutates?** — **No** = read-only; **Reports** = `reports/out/` only; **SQLite** = may write DB (often dry-run default).

---

## 1. Daily commands

Workspace: `reports/out/active/current/`. Volume: `reviewed_marketing_contacts.csv` → `send_ready_marketing.csv`. Precision: `reviewed_deepsearch.csv` → `send_ready.csv`.

| Command | Purpose | Mutates? | When |
|---------|---------|----------|------|
| `scripts/qa/prepare_outbound_campaign_workspace.py` | Init/archive `active/current/` | Reports | New outbound round |
| `cli export-dnr` | DNR lists | Reports | Volume lane start |
| `scripts/research/run_deep_research_prospecting.py` | Research batch (no send) | Reports | Weekly / daily research |
| `cli validate-csvs` | CSV contracts | No | Before process/import |
| `scripts/leads/process_broad_marketing_contacts.py` | Volume gate → send-ready | Reports | After reviewed marketing CSV |
| `scripts/leads/run_current_campaign_pipeline.py` | Precision prepare / import / post-send | Reports; SQLite with `--apply` | Named campaign |
| `scripts/leads/mark_sent_batch_contacted.py` | Post-send state | SQLite | After send |
| `cli gmail-ingest` · `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Gmail → `emails` (INBOX + Sent) | SQLite | Daily / post-send refresh |
| `cli refresh-safety` | Safety export chain | Reports | Daily / pre-send |

---

## 2. Safety / audit

| Command | Purpose | Mutates? |
|---------|---------|----------|
| `cli status` | Operator snapshot | No |
| `cli check-readiness` | Readiness | No |
| `cli daily-health` | Bundled health | Reports |
| `cli audit-overlap` | Overlap audit | Reports |
| `cli ndr-review` | NDR review batches | Reports |
| `scripts/qa/export_gate_audit_csv.py` | Gate flags sample | Reports |
| `scripts/qa/export_outreach_volume_rollup.py` | Saturation metrics | Reports |
| `scripts/qa/plan_reports_out_cleanup.py` | Plan `reports/out` | No |

---

## 3. Post-send

Order: [`POST_SEND_SAFE_LOOP.md`](pipeline/POST_SEND_SAFE_LOOP.md). Key CLI steps: `refresh-safety`, `post-send-digest`, `status`.

| Command | Purpose | Mutates? |
|---------|---------|----------|
| `cli gmail-ingest` | Ingest INBOX + Sent | SQLite |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | NDR scan / apply | SQLite (`--apply`) |
| `scripts/leads/audit_contacted_universe.py` | Exclusion CSVs | Reports |
| `cli refresh-safety` | Safety chain | Reports |
| `cli post-send-digest` | Digest artifacts | Reports |

---

## 4. Campaign-wave (OPS_MAINT)

`scripts/qa/build_presentacion_*`, `scripts/qa/build_cyber_*` — named waves only; see [`SCRIPT_MAP.md`](SCRIPT_MAP.md).

## 5. Postgres / experimental (parked)

`cli mirror-dashboard` → `sync/sync_dashboard_postgres_mirror.py` (dry-run default). Verifiers `scripts/qa/verify_*_postgres_mirror.py` — optional; [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md).

## 6. Break-glass

Send, purge, mart rebuild, broad NDR `--apply` — [`SCRIPT_MAP.md`](SCRIPT_MAP.md#break-glass-scripts). `cli build-mart` → `scripts/mart/build_business_mart.py`.

## 7. Lab / archive

`scripts/tatiana/*`, `scripts/ml/*`, `scripts/leads/campaigns/*`, archive lane — not daily outbound; [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md).
