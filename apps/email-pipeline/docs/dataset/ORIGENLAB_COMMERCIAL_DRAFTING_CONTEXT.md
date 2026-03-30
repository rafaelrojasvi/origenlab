# OrigenLab commercial drafting context (source-of-truth layer)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-29

<a id="m-ol-draft-scope"></a>
## Purpose

This document defines how **Tatiana drafting** connects to the **OrigenLab monorepo** as a commercial tool — aligned with the email/archive platform and web data, not as an isolated experiment.

The **OrigenLab drafting context layer** separates:

| Layer | Role |
|--------|------|
| **Company facts** | Approved identity, geography, contact, positioning — loaded from `apps/web/src/data/*.ts` |
| **Commercial policy** | Short rule mirror of [`docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](../../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md) (full policy remains that doc) |
| **Product / catalog facts** | High-level lines from `categories.ts`, `brands.ts`, `products.ts` — only what exists in repo; never invented |
| **Historical email examples** | **Style and structure only** (TF-IDF retrieval from Tatiana cohort seeds) — **not** factual truth or current identity |

Human-readable summary for humans and external prompts: [`apps/web/docs/company-scope.md`](../../../web/docs/company-scope.md).

---

## Code entry points

| Module | Responsibility |
|--------|----------------|
| [`tatiana_copilot/origenlab_context.py`](../../src/origenlab_email_pipeline/tatiana_copilot/origenlab_context.py) | `OrigenLabDraftingContext` dataclass, policy bullet factory |
| [`tatiana_copilot/origenlab_facts_loader.py`](../../src/origenlab_email_pipeline/tatiana_copilot/origenlab_facts_loader.py) | Load facts from monorepo web data paths (no network) |
| [`tatiana_copilot/prompting.py`](../../src/origenlab_email_pipeline/tatiana_copilot/prompting.py) | Prompt package: labels examples as `STYLE_REFERENCE_ONLY_NOT_FACTS` in OrigenLab mode |
| [`tatiana_copilot/openai_chat_generator.py`](../../src/origenlab_email_pipeline/tatiana_copilot/openai_chat_generator.py) | System prompt + signature normalization for `origenlab` vs historical Tatiana |
| [`tatiana_copilot/pilot_batch.py`](../../src/origenlab_email_pipeline/tatiana_copilot/pilot_batch.py) | `--origenlab` on CLI; writes `origenlab_context_snapshot.json` per batch |

---

## Historical cohort mode vs OrigenLab mode

| | **Default (historical / Tatiana)** | **`--origenlab`** |
|--|--|--|
| Instruction | Tatiana / Labdelivery voice; examples are style-only | OrigenLab B2B voice; **no** Labdelivery identity |
| Signature (post-process) | Canonical Tatiana historic block | **Approved OrigenLab** block from loaded context |
| Company facts in prompt | Not injected | **`company_facts`** + **`commercial_policy`** from repo |
| Case supplements | `case` + metadata | Same + **`case_context_supplement`** when columns are present |

Default mode remains backward compatible for eval and cohort pilots.

---

## Pilot input: current-company CSV

Template: **[`config/origenlab_pilot_input.example.csv`](../../config/origenlab_pilot_input.example.csv)**.

Recommended columns: `requester_name`, `requester_email`, `requested_product_or_category`, `explicit_known_facts`, `missing_information`, `notes_for_reviewer` (see [`pilot_loader.py`](../../src/origenlab_email_pipeline/tatiana_copilot/pilot_loader.py) aliases).

**No live inbox sync** in this layer: CSVs are manual or from future exports. SQLite / marts ([`BUSINESS_MART.md`](../pipeline/BUSINESS_MART.md)) are the natural future source for case derivation.

---

## Commands (from `apps/email-pipeline`)

OrigenLab-mode pilot (mock):

```bash
uv run python scripts/tatiana/run_tatiana_pilot_batch.py \
  --input config/origenlab_pilot_input.example.csv \
  --origenlab \
  --allow-mock \
  --max-cases 5
```

Provider-backed: omit `--allow-mock`; same API key setup as [`TATIANA_PILOT_WORKFLOW.md`](TATIANA_PILOT_WORKFLOW.md).

---

## Not implemented

- Email **send** or IMAP **auto-reply**
- Full inbox assistant
- Loading company facts from SQLite (this version uses **`apps/web/src/data/*.ts`** only)

---

## Related

- [`TATIANA_PILOT_WORKFLOW.md`](TATIANA_PILOT_WORKFLOW.md) · [`TATIANA_DRAFTING_COPILOT.md`](TATIANA_DRAFTING_COPILOT.md) · [`../../../../docs/PROJECT_CONTEXT.md`](../../../../docs/PROJECT_CONTEXT.md)
</think>


<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace