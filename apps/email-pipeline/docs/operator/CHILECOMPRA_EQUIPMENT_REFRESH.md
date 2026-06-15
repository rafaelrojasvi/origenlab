# ChileCompra equipment queue refresh (operator)

Automated operator step to refresh the equipment-first queue from the Mercado Público licitaciones API, publish the canonical dashboard CSV, and let the existing dashboard auto-mirror job push changes to Postgres.

## Required environment

- `CHILECOMPRA_API_TICKET` — Mercado Público API ticket. Read from the environment only; never commit or print in logs.

## Manual command

Dry-run (no API calls, no writes):

```bash
cd apps/email-pipeline
uv run origenlab auto-refresh-chilecompra-equipment --once
```

Apply (fetch, write API queue + audit, publish canonical dashboard CSV, update manifest):

```bash
cd apps/email-pipeline
uv run origenlab auto-refresh-chilecompra-equipment --once --apply
```

Operator shell wrapper:

```bash
apps/email-pipeline/scripts/operator/run_auto_refresh_chilecompra_equipment.sh
```

Useful flags:

- `--max-details 50` — conservative detail lookup cap (default)
- `--detail-sleep-seconds 3` — pause between detail lookups
- `--detail-cache-dir reports/out/active/current/chilecompra_detail_cache`
- `--no-publish` — build API queue only; skip canonical dashboard publish
- `--force` — bypass cooldown
- `--cooldown-seconds 7200` — default daytime cooldown between successful applies

## Recommended cron timing

Do **not** add cron entries in code — schedule externally when ready.

Suggested starting point for daytime operations:

- Every **2–4 hours** during business hours, **not** on the same minute as `auto-mirror-dashboard`.
- Example pattern: refresh ChileCompra at `:20`, mirror dashboard at `:35` every 2 hours.

Keep `max-details` conservative (50 or lower) to respect API quotas.

## Quota caution

- Summary list + per-codigo detail lookups consume Mercado Público API quota.
- Detail cache under `reports/out/active/current/chilecompra_detail_cache/` reduces repeat lookups.
- Review `chilecompra_equipment_candidate_audit_YYYYMMDD.csv` when tuning `max-details`.

## Dashboard mirror relationship

This command **does not** call `auto-mirror-dashboard` or write to Postgres directly.

After publish with manifest update, `auto-mirror-dashboard` detects the dashboard input fingerprint change (`manifest.json` + canonical equipment queue) and mirrors to Postgres on its own schedule.

## Safety

- Review-only semantics: published rows use `review_required` / `mercado_publico_only`.
- **Never contact buyers outside Mercado Público** unless explicitly allowed and reviewed.
- No Gmail send, campaign send, purge, or contact approval in this workflow.
- State: `reports/out/active/current/chilecompra_equipment_auto_refresh_state.json`
- Lock: `reports/out/active/current/chilecompra_equipment_auto_refresh.lock`
