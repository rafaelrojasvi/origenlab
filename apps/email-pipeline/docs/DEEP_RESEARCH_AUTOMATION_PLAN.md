# Deep Research Automation Plan

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-29

## Scope

This plan defines a recurring automation that creates **review-ready** prospecting batches for OrigenLab using OpenAI Deep Research and the existing volume marketing lane safeguards.

## What is automated

1. Render a configurable Deep Research prompt from a template file.
2. Run OpenAI Responses API Deep Research with `web_search`.
3. Pass current seed CSVs as model file inputs.
4. Save raw model outputs to timestamped run folders.
5. Extract candidate CSV rows from model output.
6. Perform local exclusion re-check against DNR/contacted/known files.
7. Validate net-new candidates with `validate_campaign_csvs.py --strict`.
8. Process net-new candidates with `process_broad_marketing_contacts.py` (read-only gate context).
9. Generate a compact markdown `review_summary.md`.
10. Stop with: `Ready for review; no live send performed.`

## Guardrails (Stage 1.1)

New CLI safety limits:

- `--max-candidates` (default `200`)
- `--max-send-ready` (default `50`)
- `--fail-on-over-limit`

Behavior:

- If extracted candidates exceed `--max-candidates`:
  - default: truncate to max and record warning/flags in summary + metadata
  - with `--fail-on-over-limit`: fail fast and stop run
- If send-ready rows exceed `--max-send-ready`:
  - run still stops before send (always)
  - summary + metadata mark over-limit clearly for reviewer action

CSV hardening:

- Handles markdown ` ```csv ` fences, leading/trailing prose, and UTF-8 BOM.
- Normalizes harmless header variants.
- Requires expected marketing schema; invalid schema fails clearly.

## What is NOT automated

- Live Gmail API send.
- `mark_sent_batch_contacted.py`.
- Sent ingest (`05_workspace_gmail_imap_to_sqlite.py`).
- Post-send DNR refresh flow.
- Any `--apply` mutations.
- Schema changes, migrations, or destructive deletes.

## Seed files used

Default seed paths:

- `reports/out/active/current/do_not_repeat_master.csv`
- `reports/out/active/outreach_contacted_all.csv`
- `reports/out/active/all_known_marketing_contacts_dedup.csv`

CLI supports overrides with:

- `--seed-dnr`
- `--seed-contacted`
- `--seed-known-marketing`

## Recommended schedule

- Daily morning run in Chile business hours (for example 08:00 America/Santiago).
- Keep this review-first: generate prospects daily, but send only after human approval.
- Run early enough to allow same-day review and curation.

Recommended weekday sector rotation (scheduler-driven):

- Monday: `broad`
- Tuesday: `water_env`
- Wednesday: `universities_regional`
- Thursday: `hospitals_clinical`
- Friday: `industry_qc`
- Saturday: `thin_regions`
- Sunday: `custom` (or dry-run smoke check)

Use `--day-rotation` for simple day-of-week automatic sector mapping.

## Canonical exclusion source

- Treat `reports/out/active/current/do_not_repeat_master.csv` as the canonical outbound do-not-repeat seed.
- Treat `outreach_contacted_all.csv` and `all_known_marketing_contacts_dedup.csv` as auxiliary artifacts for overlap visibility and additional exclusion context.
- Use read-only `scripts/qa/validate_contacted_csv_coverage.py` to surface drift/coverage mismatches between these CSVs and Sent truth.

## Outputs produced

Run folder default:

- `reports/out/active/current/research_automation/<timestamp>/`

Artifacts:

- `raw_response.json`
- `raw_response.txt`
- `candidates_raw.csv`
- `candidates_netnew.csv`
- `candidates_excluded.csv`
- `validation_result.json`
- `process_workspace/send_ready_marketing.csv`
- `process_workspace/marketing_blocked_already_known.csv`
- `process_workspace/marketing_contacts_summary.json`
- `review_summary.md`
- `run_metadata.json`

## Safety stop before send

The automation exits after building review artifacts and never calls sender/post-send tools.

Final terminal message:

`Ready for review; no live send performed.`

## Required env vars

For live research calls (non-dry-run):

- `OPENAI_API_KEY` (or `ORIGENLAB_TATIANA_OPENAI_API_KEY`)

Existing pipeline env/config remains unchanged for validator/processor safety checks.

## Manual test workflow

From `apps/email-pipeline`:

```bash
uv run python scripts/research/run_deep_research_prospecting.py \
  --dry-run \
  --sample-response tests/fixtures/research_automation/sample_response.txt \
  --sector broad \
  --max-candidates 50 \
  --max-send-ready 20
```

Then inspect:

- `review_summary.md`
- `candidates_excluded.csv`
- `process_workspace/send_ready_marketing.csv`

Optional read-only coverage drift check during run:

- `--run-contacted-coverage-check`
- add `--strict-contacted-coverage` only if you want the run to fail on validator non-zero status

## Local scheduling handoff

Example cron patterns are documented in:

- `scripts/research/cron_example.txt`

Notes:

- Verify host timezone.
- If host timezone is not America/Santiago, use explicit TZ handling at scheduler level.
- This job only creates review-ready batches; it does not send.

