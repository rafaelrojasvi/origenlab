# Tatiana Draft Eval Review (manual scoring)

This doc explains how to manually score `eval_cases.csv` outputs produced by the Tatiana drafting copilot.

## Files

When you run an eval:

- `reports/out/<timestamp>_tatiana_draft_eval/eval_cases.csv`
- `reports/out/<timestamp>_tatiana_draft_eval/eval_summary.json`
- `reports/out/<timestamp>_tatiana_draft_eval/eval_*.json` (per-case draft packages)

You fill in manual columns in `eval_cases.csv` and then run the summarizer.

## Reviewer columns (rubric)

Fill these columns (leave blank if you did not review a row yet):

- `reviewer_score_tone` (1–5): 1 = wrong tone, 5 = perfect Tatiana-like tone
- `reviewer_score_usefulness` (1–5): 1 = unusable, 5 = immediately useful
- `reviewer_score_groundedness` (1–5): 1 = hallucinated / unsafe, 5 = fully grounded
- `reviewer_score_edit_distance_estimate` (1–5):
  - 1 = tiny edits
  - 2 = light edits
  - 3 = moderate edits
  - 4 = heavy edits
  - 5 = rewrite needed
- `reviewer_decision` (enum):
  - `accept`
  - `edit_light`
  - `edit_heavy`
  - `reject`
- `notes` (free text): your explanation; used for failure bucket heuristics.

## Important: `system_notes` vs `notes`

- `system_notes` is written by the pipeline (e.g. mock template, abstain reasons).
- `notes` is **yours** (manual review comments).

## Identical mock drafts (batch scoring)

With `MockDraftGenerator`, the **body** is often the same on every row; only the `Asunto:` line may differ (including MIME). Re-entering the same scores 30 times is optional.

1. See how many rows share the same body (first line `Asunto:` is ignored for grouping):

   ```bash
   uv run python scripts/tatiana/score_tatiana_eval_cases_cli.py \
     --eval-dir reports/out/<timestamp>_tatiana_draft_eval \
     --show-draft-groups
   ```

2. Score **one** representative row, then use **`--batch-same-body`**: after each scored row, the CLI can copy reviewer fields + `notes` to all other rows whose draft body matches.

   ```bash
   uv run python scripts/tatiana/score_tatiana_eval_cases_cli.py \
     --eval-dir reports/out/<timestamp>_tatiana_draft_eval \
     --only-unscored \
     --batch-same-body
   ```

   Answer `y` when prompted to fill the rest. With `--only-unscored`, already-scored rows are not overwritten by the batch step.

## Summarize a scored eval

From `apps/email-pipeline`, after you fill scores:

```bash
uv run python scripts/tatiana/summarize_tatiana_eval_review.py \
  --eval-dir reports/out/<timestamp>_tatiana_draft_eval
```

Outputs in:

- `reports/out/<timestamp>_tatiana_draft_eval/review_summary/`
  - `review_summary.json`
  - `review_summary.md`
  - `review_failures.csv`
  - `review_priority_cases.csv`

## Failure buckets (heuristic)

Buckets are deterministic and transparent:

- note keyword mapping first (e.g. “falta info”, “muy genérico”, “alucina”)
- then score/decision inference:
  - low groundedness → `grounding_risk`
  - reject/heavy edit + high edit-distance → `rewrite_required`
  - very low usefulness → `too_generic`

## Recommendation logic

The summarizer emits a recommendation like:

- `ready_for_provider_pilot`
- `needs_prompting_iteration`
- `needs_retrieval_iteration`
- `needs_dataset_cleanup`
- `insufficient_review_data`

Logic is threshold-based and written into `review_summary.json` under `recommendation.thresholds`.

