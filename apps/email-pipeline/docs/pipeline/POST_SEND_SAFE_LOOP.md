# Post-send safe loop

Status: canonical (operator procedure)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-02

**Purpose:** Refresh operational truth after **new outbound mail**, **NDR/bounces**, or **suppression changes**. Use this loop so SQLite safety sidecars, exclusion CSVs, digest, and Postgres mirror match Gmail evidence.

**Not enough alone:** mirror-only refresh when Gmail changed — ingest + NDR review + safety exports must run first.

Related: [`CURRENT_SAFETY_CHECKPOINT.md`](CURRENT_SAFETY_CHECKPOINT.md) · [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md) · [`SCRIPT_MAP.md`](../SCRIPT_MAP.md)

---

## Golden rule

When **Sent mail or INBOX NDRs changed**, run the **full loop** below (at least through safety memory + contacted audit + mirror). **`RUN_GMAIL_INGEST=0` mirror-only** is for presentation refresh only, not post-campaign safety.

**Send gates:** `contact_email_suppression`, `contact_domain_suppression`, `outreach_contact_state`, export gates — **not** `lead_research_prospect.classification`. **Dashboard LISTO / mirror_ok is not send approval.**

---

## Steps (from `apps/email-pipeline/`)

| # | Step | Command / script |
|---|------|------------------|
| 1 | **Gmail ingest (read-only IMAP)** | `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder INBOX --since-days N --skip-duplicate-message-id` then same for `[Gmail]/Enviados`. No `--replace-source`. |
| 2 | **NDR dry-run** | `uv run python scripts/tools/flag_ndr_bounces_from_contacto.py --since-days N` (default: print-only) |
| 3 | **Review proposed suppressions** | Read output; classify permanent vs delay vs `bounce_other`; build allowlist if applying |
| 4 | **Apply exact suppressions (operator-approved only)** | Targeted: `--emails-file PATH --only-code bounce_no_such_user` (or `bounce_other`) **`--apply`**. See [NDR apply rules](#ndr-apply-rules). |
| 5 | **Contacted universe** | `uv run python scripts/leads/audit_contacted_universe.py` |
| 6 | **Safety memory** | `uv run python scripts/qa/refresh_outbound_safety_memory.py` |
| 7 | **Post-send digest** | `uv run python scripts/qa/build_post_send_digest.py --since-days N` (**after** step 5) |
| 8 | **Mirror (Gmail ingest off)** | `GMAIL_SINCE_DAYS=0 RUN_GMAIL_INGEST=0 DASHBOARD_FAST=1 RUN_LEAD_RESEARCH_MIRROR=1 RUN_OUTBOUND_SIDECAR_MIRROR=1 bash scripts/ops/refresh_render_dashboard_once.sh` |
| 9 | **Prospectos drift (read-only)** | `uv run python scripts/qa/audit_prospectos_safety_drift.py` — drift ≠ send failure |
| 10 | **Operator status + verifiers** | `uv run python scripts/qa/operator_status.py`; check `/tmp/outbound_sidecar_mirror_verify.json`, `/tmp/lead_research_mirror_verify.json`, `/tmp/render_dashboard_mirror_verify.json` (`ok` / assertions passed) |

Adjust `N` (`--since-days`) to cover the campaign window (often `1`–`2`).

---

## NDR apply rules

| Rule | Detail |
|------|--------|
| **Dry-run first** | Default script mode writes **no** SQLite rows. |
| **Targeted apply (preferred)** | `--emails-file` one email per line + `--only-code CODE` + `--apply`. Allowlist emails **must** appear in current NDR scan evidence or apply is **refused**. |
| **Broad `--apply` (break-glass)** | `--apply` **without** `--emails-file` / `--only-code` upserts **all** planned recipients from the scan — treat as legacy / high risk; operator review required. |
| **Exact-email only** | NDR apply writes `contact_email_suppression` per address — **not** domain suppression. |
| **Delay DSNs** | Subjects with `Notification (Delay)` / `(delay)` are **skipped** — wait for final failure NDR. |
| **Unparsed NDR** | No recipient extracted → no suppression from that row. |

Example (after review):

```bash
uv run python scripts/tools/flag_ndr_bounces_from_contacto.py \
  --since-days 1 \
  --emails-file reports/in/manual_reviews/my_allowlist.txt \
  --only-code bounce_no_such_user \
  --apply
```

Allowlist files under `reports/in/` are **gitignored** — do not commit.

---

## Historical orchestrator (do not copy blindly)

[`scripts/ops/run_post_send_2026_06_01_refresh.sh`](../../scripts/ops/run_post_send_2026_06_01_refresh.sh) is a **2026-06-01 one-off**. It still runs **broad NDR `--apply`** in step 2. For new waves, follow **this doc** and use targeted allowlists — do not assume that shell is the canonical apply path.

---

## What this loop does not do

- Send mail or create Gmail drafts  
- Import `reports/in/manual_reviews/` institution packs without explicit approval  
- Create `institution_alias` tables or domain-wide NDR blocks  
