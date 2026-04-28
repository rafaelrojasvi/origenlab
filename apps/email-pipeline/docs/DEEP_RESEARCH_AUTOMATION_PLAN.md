# Deep Research Automation Plan

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-28

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

- Weekly Monday morning in Chile business hours (for example 08:00 America/Santiago).
- Run early enough to allow human review and curation before any manual send wave.

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
  --sector broad
```

Then inspect:

- `review_summary.md`
- `candidates_excluded.csv`
- `process_workspace/send_ready_marketing.csv`

## Local scheduling handoff

Example cron patterns are documented in:

- `scripts/research/cron_example.txt`

Notes:

- Verify host timezone.
- If host timezone is not America/Santiago, use explicit TZ handling at scheduler level.
- This job only creates review-ready batches; it does not send.

