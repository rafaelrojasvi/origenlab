# Tatiana pilot batch (human-reviewed provider drafts)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-29

<a id="m-tatiana-pilot-scope"></a>
## OrigenLab scope

This is the **operational pilot** path for OrigenLab’s **Tatiana commercial drafting** capability (see [`TATIANA_DRAFTING_COPILOT.md`](TATIANA_DRAFTING_COPILOT.md)): small batches of real candidate cases, provider-backed drafts when configured, and **explicit human decisions** recorded in CSV. It is part of the same monorepo as the **email archive / lead pipeline** and **web presence** — not a detached experiment. Outbound send, CRM updates, and inbox automation remain **out of scope** for this repo; `approved_for_send` is tracking only.

- Monorepo: [`docs/PROJECT_CONTEXT.md`](../../../../docs/PROJECT_CONTEXT.md)
- Commercial truth policy: [`docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](../../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md)

---

This workflow generates **draft suggestions** for a **small batch of real candidate emails**, exports artifacts for **mandatory human review**, and summarizes reviewer decisions. It does **not** send email, connect to CRM, or auto-reply.

## Principles

- **No autonomous sender** — final send is always outside this pipeline.
- **`approved_for_send`** is a **tracking field only**; nothing in this repo acts on it.
- Default generation uses the **OpenAI Chat** draft generator when configured; use **`--allow-mock`** only for tests or intentional offline batches.
- Retrieval uses the same local **TF-IDF index** and seed CSVs as eval (`tatiana_candidate_cohort_marketing_top200_*`).

## Pilot milestone (mock → provider → cohort)

Use this sequence to confirm the **full path** is healthy:

1. **Mock** — `run_tatiana_pilot_batch.py` with `--allow-mock` and `config/tatiana_pilot_input.example.csv` checks packaging, retrieval, and writes **without** an API.
2. **Provider on demo** — same input **without** `--allow-mock` checks keys, model id, and real `openai_chat` drafts.
3. **Provider on cohort-derived CSV** — run `prepare_tatiana_pilot_input.py`, then point `--input` at that file (e.g. `reports/out/pilot_input_example.csv`). A strong sign is JSON like **`generator_name`: `openai_chat`**, **`cases_processed`** matching your `--max-cases` (or full file), and an **`abstained_count`** you accept for that batch.

After step 3 succeeds, the next question is **not** “does the script run?” but **whether the drafts are useful in OrigenLab terms once a human reviews them** (tone, grounding, policy). That is what steps 3–4 (review + summarize) answer.

## Historical cohort vs live inbox

Input built from **`tatiana_candidate_cohort_marketing_top200_*`** is **commercial drafting on curated, archive-style cases** (Tatiana / marketing cohort), **not** a live **today’s inbox** assistant. There is no automatic ingest from a live mailbox in this workflow; everything is **file in, artifacts out**. After a good cohort pilot, the natural next step is a **pilot CSV built from current company cases** (still file-driven and human-reviewed) if you need live-representative evaluation.

## Input formats

### CSV (recommended)

UTF-8, header row. Canonical columns:

| Column | Required | Notes |
|--------|----------|--------|
| `case_id` | yes | Stable id (or use `id`) |
| `subject` | no | May be empty |
| `body_text` | yes | May also use `body` or `body_for_review` |
| `from_email` | no | Aliases: `sender_email`, `email` |
| `from_name` | no | Aliases: `sender_name`, `name` |
| `thread_hint` | no | Free text / opaque id |
| `received_at` | no | Aliases: `date_iso`, `sent_at` |
| `case_type` | no | Aliases: `expected_mode`, `expected_label` |
| `notes` | no | Internal notes |

Extra columns are preserved inside the per-case JSON under `case.context_metadata` (from the pilot loader).

### JSONL

One JSON object per line; same keys as CSV (aliases apply).

### JSON batch

Either a list `[{...}, ...]` or `{"cases": [{...}, ...]}`.

## Commands

From `apps/email-pipeline`:

### 1) (Optional) Build pilot input from cohort export

```bash
uv run python scripts/tatiana/prepare_tatiana_pilot_input.py \
  --cohort-csv reports/out/tatiana_candidate_cohort_marketing_top200_labeled_final.csv \
  --out reports/out/pilot_input_example.csv \
  --limit 10
```

Edit the CSV if needed; remove rows you do not want in the pilot.

### 2) Run pilot batch (provider-backed)

Requires API key (see `.env.example`): `ORIGENLAB_TATIANA_OPENAI_API_KEY` or `OPENAI_API_KEY`.

```bash
EVAL_DIR=reports/out
uv run python scripts/tatiana/run_tatiana_pilot_batch.py \
  --input reports/out/pilot_input_example.csv \
  --max-cases 10
```

Writes a folder like `reports/out/YYYYMMDD_HHMMSS_tatiana_pilot_batch/` (UTC). The JSON printed on stdout includes the exact **`out_dir`**.

Each successful run also updates a symlink **`reports/out/latest_tatiana_pilot_batch`** → that folder (same base as `ORIGENLAB_REPORTS_DIR` if set).

### 2b) Mock batch (tests / no API)

Use a real path: `path/to/...` in README snippets is only a placeholder. For a **tracked synthetic file** (no API key), use `config/tatiana_pilot_input.example.csv`.

```bash
uv run python scripts/tatiana/run_tatiana_pilot_batch.py \
  --input config/tatiana_pilot_input.example.csv \
  --allow-mock \
  --max-cases 5
```

Or point `--input` at a CSV you built in step 1 (e.g. `reports/out/pilot_input_example.csv`).

`--generator mock` without `--allow-mock` is **rejected** to avoid silent offline runs.

### 2c) OrigenLab-native mode (`--origenlab`)

Injects **company facts and policy** from `apps/web/src/data/*.ts` into the prompt package; forces **OrigenLab signature** (not Labdelivery). Historical cohort retrieval stays **style-only** (see [`ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md`](ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md)).

```bash
uv run python scripts/tatiana/run_tatiana_pilot_batch.py \
  --input config/origenlab_pilot_input.example.csv \
  --origenlab \
  --allow-mock \
  --max-cases 5
```

Each batch writes **`origenlab_context_snapshot.json`** next to `pilot_summary.json`.

### 3) Human review

In the batch folder (the `out_dir` from the JSON stdout, or `reports/out/latest_tatiana_pilot_batch`), open first:

- **`pilot_review.csv`** — main sheet for decisions
- **`pilot_summary.md`** — generation pass metadata
- **`case_<case_id>.json`** — full per-case `DraftPackage` (retrieval, draft, abstention)

Then fill **`pilot_review.csv`** columns:

- `reviewer_decision`: `approve` | `approve_with_edits` | `reject` | `needs_clarification`
- `reviewer_edit_level`: `none` | `light` | `moderate` | `heavy`
- `reviewer_sentiment`: `good` | `mixed` | `poor`
- `reviewer_notes`, `reviewer_final_subject`, `reviewer_final_body`
- `approved_for_send`: `y` | `n` (tracking only)

### 4) Summarize review

**Do not paste** `reports/out/<timestamp>_...` into the shell: in zsh/bash, `<` starts **input redirection**, which triggers errors like `no such file or directory: timestamp`.

**Option A — latest pilot** (after a local `run_tatiana_pilot_batch`; uses the symlink above):

```bash
uv run python scripts/tatiana/summarize_tatiana_pilot_review.py
```

**Option B — explicit folder** (use the real directory name or copy `out_dir` from the batch JSON):

```bash
uv run python scripts/tatiana/summarize_tatiana_pilot_review.py \
  --pilot-dir reports/out/20260329_184654_tatiana_pilot_batch
```

Writes **`pilot_review_summary.json`** and **`pilot_review_summary.md`** in that folder (or `--out-dir`).

## Output layout

```
YYYYMMDD_HHMMSS_tatiana_pilot_batch/
  pilot_cases.csv          # machine audit (previews + paths)
  pilot_review.csv         # human review sheet
  pilot_summary.json       # generation pass metadata
  pilot_summary.md
  case_<case_id>.json      # full DraftPackage per case
  pilot_review_summary.*   # after step 4
```

## Tests

```bash
uv run pytest tests/test_tatiana_pilot_batch.py -q
```

## Suggested first real pilot size

**5–10 cases**: enough signal, low cost; expand after one review cycle.

## Known limitations

- Retrieval pool is the **same marketing seed** as eval; not tuned per inbox.
- Long bodies in CSV are quoted; Excel/LibreOffice should handle UTF-8.
- Summarizer **note buckets** are keyword heuristics, not NLP.
- Recommendations are **transparent rules**, not ML.

## Related

- Drafting overview: `TATIANA_DRAFTING_COPILOT.md`
- **OrigenLab facts / `--origenlab` mode:** [`ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md`](ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md)
- Eval scoring: `TATIANA_EVAL_REVIEW.md`
