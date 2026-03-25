# Tatiana candidate writing cohort (manual review)

Operational definition for **`export_tatiana_candidate_cohort.py`**. This cohort is **not** the same as strict SQL `explore_email_clusters.py --sample-mode voice` (From-domain-only slice, mostly phishing in this archive).

## Inclusion (must match `is_voice_candidate_row`)

Exactly one path (or more) from `tatiana_voice_cohort.py`:

1. **Address allowlist** — `ORIGENLAB_TATIANA_SENDERS`, `ORIGENLAB_TATIANA_SENDERS_FILE`, or `config/tatiana_senders.local.txt`.
2. **Voice sender domains** — `config/voice_sender_domains.txt`, `voice_sender_domains.local.txt`, env `ORIGENLAB_VOICE_SENDER_DOMAINS` (+ optional file env).
3. **Optional text signals** (`--include-tatiana-text-signals`) — whole-word **Tatiana** or **Vivanco** in From line or in `full_body_clean` / `top_reply_clean`, while the From domain is in **trusted** set (`INTERNAL_DOMAINS` ∪ voice domains).

Shared mailboxes on `origenlab.cl` (`contacto@`, `info@`, `ventas@`) are **excluded** unless `--allow-shared-mailboxes`.

## Export filters (after inclusion)

- **`--min-len-hybrid`** (default **120**): minimum length of `hybrid_style_body(full_body_clean, top_reply_clean)` (see `tatiana_voice_cohort.hybrid_style_body` for field choice).
- **`--exclude-noise`**: drop rows matching `is_noise_sender` (NDR / obvious operational noise).
- Optional **`--max-rows`**: keep the top-N rows after **exact deduplication** (see below). Sort order is by **`review_quality_score`** (general mode) or by **marketing rank** (`--target-use-case marketing`).

## Duplicate suppression (export)

After scoring and sorting, the export drops **exact duplicates** so one thread snippet does not fill the top of the CSV. A row is a duplicate if this key matches a prior row:

- whitespace-normalized, lowercased **`body_for_review`**, plus normalized **subject**, plus **calendar day** from **`date_iso`** (first 10 characters).

The **first** row in sort order wins (best row under the active sort — general score or marketing tuple). Summary JSON includes **`rows_before_exact_dedup`** and **`rows_dropped_duplicate_exact`**.

## Exclusion / downranking (heuristic, not hard drop unless noted)

Hard drops are only **inclusion + optional noise + min length**. Everything else is **risk flags** and **score** penalties:

- **Spoof / phishing templates** in subject or body (Chilexpress-style lures, fake admin, “Si no está viendo…”, etc.) → `risk_flags`, large score penalty.
- **`classify_email` noise primaries** (bounce, spam_suspect, newsletter, social) → flags + penalty.
- **Heavy quoted thread** in full body (`>` line ratio) → flag + penalty.
- **Trivial one-liner** hybrid → flag + penalty.
- **Forward / reply noise in `body_for_review`** (`De:` / `From:` / `Enviado el:` / dense `>` lines, etc.) → `risk_flags` such as `hybrid_opens_forward_header`, `hybrid_forward_or_quote_heavy`, … + score penalty (see `tatiana_review_cohort.hybrid_thread_contamination`).
- **Mostly English commercial prose** when Spanish markers are weak → `likely_non_spanish_commercial_body` + mild penalty (`non_spanish_commercial_downrank`).

**Outbound hint:** `likely_outbound_external` = at least one recipient domain outside `INTERNAL_DOMAINS` ∪ voice domains — weak signal (headers are lossy). The ranker **boosts** external-facing rows and **downranks** `internal` when there is **no** external recipient; **`business_core`** gets an extra boost when outbound.

**Invoice / payment ops:** invoice-style subtype or invoice intent **without** external recipients is **downranked** relative to quote/follow-up style mail.

## CSV columns (review)

Use **`sender`** and **`recipients`** for From/To (not `from` / `to`). Other useful columns: **`body_for_review`**, **`review_quality_score`**, **`intent_*`**, **`risk_flags`**, **`date_iso`**.

## Body field for review

**`body_for_review`** is always **`hybrid_style_body`**: balances reply-only text vs signature tail in full body (see module docstring in `tatiana_voice_cohort.py`).

## Scoring (`review_quality_score`, 0–100)

Transparent heuristic for **sorting spreadsheets only** — not ground truth. Higher ≈ more useful for **Spanish commercial / intro / quote-style** review *after* filters. Components include: identity path strength, **stronger weight on outbound + `business_core`**, **downrank `internal` without external recipients**, quote/follow-up / outbound support boosts, invoice-without-outbound penalties, hybrid length bands, and penalties for noise, spoof hints, heavy quotes, forward/thread contamination, non-Spanish commercial tone, trivial length.

Cohort version is recorded in summary as **`tatiana_candidate_cohort_version`** (see `TATIANA_CANDIDATE_COHORT_VERSION` in code).

Tune **`--high-confidence-min-score`** for summary counts only (default 62).

## Marketing / intro / prospecting export (optional)

Same **inclusion** and base **`review_quality_score`** as the general export; **only sort order and extra CSV columns** change.

**Flags:** `--target-use-case marketing` or **`--prefer-marketing`** (either enables the mode; `--prefer-marketing` forces marketing even if `--target-use-case general` were passed).

**Default output file:** `reports/out/tatiana_candidate_cohort_marketing_<ts>.csv` (and `_summary.json`).

**`marketing_rank_delta`** is added to **`review_quality_score`** for ordering only (base score in the CSV is unchanged). **Tie-break** (when combined scores cluster) uses, in order: **`marketing_export_tier`**, fresh subject (**`subject_reply_or_forward` = n** preferred), **lower** `ops_noise_hits`, **lower** hybrid contamination flag count, **higher** external recipient domain count, **longer** hybrid body, then stable **`id`**.

**Demotions (delta):** phrases around **transferencias / comprobantes / datos bancarios**, **cobranza / pago factura**, **aduana / guía / courier / DHL coordination**, **proforma + destinatario/despacho** edits, plus a small extra hit when **`intent_invoice`** without quote intent. Caps apply so a single row cannot absorb unlimited penalties.

**Boosts (delta):** **non–reply/forward subject** (including common MIME-encoded `Re:`), **“gracias por contactarnos”**, **junto con saludar + cotización/adjunto**, **representante/importador/distribuidor** language on a fresh thread, **`quote` / `followup`** subtype when not already heavily demoted.

**Extra CSV columns (marketing mode only):** `marketing_rank_delta`, `marketing_export_tier`, `subject_reply_or_forward`, `marketing_rank_score` (= score + delta), `marketing_rank_notes` (semicolon-separated tags).

## Commands

```bash
cd apps/email-pipeline
uv run python scripts/dataset/export_tatiana_candidate_cohort.py --exclude-noise --include-tatiana-text-signals
```

Optional cap for a first pass:

```bash
uv run python scripts/dataset/export_tatiana_candidate_cohort.py --exclude-noise --include-tatiana-text-signals --max-rows 500
```

Marketing-first slice (same filters, re-ranked for intro/quote-style review):

```bash
uv run python scripts/dataset/export_tatiana_candidate_cohort.py --exclude-noise --include-tatiana-text-signals --max-rows 500 --prefer-marketing
```

Outputs:

- `tatiana_candidate_cohort_<ts>.csv` — general mode; UTF-8, full `body_for_review`.
- `tatiana_candidate_cohort_marketing_<ts>.csv` — marketing mode; same plus `marketing_rank_*` columns.
- Matching `*_summary.json` — counts, buckets, `filters.target_use_case`, risk flag histogram.

### Quick check of top rows

Use **`sender`** and **`recipients`** (not `from` / `to`). Replace `<ts>` with the export timestamp:

```bash
cd apps/email-pipeline
python3 - <<'PY'
import csv
from pathlib import Path
p = Path("reports/out/tatiana_candidate_cohort_<ts>.csv")
with p.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
for i, r in enumerate(rows[:20], 1):
    print(i, r.get("date_iso"), r.get("review_quality_score"), r.get("intent_primary_category"), r.get("marketing_rank_score", ""))
    print("  sender:", (r.get("sender") or "")[:120])
    print("  risk_flags:", r.get("risk_flags"))
    print("  mk_notes:", r.get("marketing_rank_notes", ""))
PY
```

For a **marketing** CSV, expect **higher `marketing_rank_score`** at the top to track quote/intro-friendly rows; **`marketing_rank_notes`** shows demotions (`mk_demote:*`) and boosts (`mk_boost:*`). Payment/transfer threads should fall relative to the same run in **general** mode.

## Related scripts

- `audit_tatiana_identity_signals.py` — DB-wide identity mention stats.
- `report_tatiana_cohort_metrics.py` — counts / buckets without export.
- `export_tatiana_review_sample.py` — **stratified small sample** for labeling (different from full candidate export).
