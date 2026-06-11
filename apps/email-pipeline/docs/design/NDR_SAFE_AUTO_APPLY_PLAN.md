# NDR safe auto-apply — design plan

Status: **design only** — no behavior enabled yet  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-11  
Area: `apps/email-pipeline`

**Purpose:** Define a staged, guarded path toward automating **only the safest** NDR suppression applies. Broad `--apply` remains forbidden. This document does **not** change runtime behavior.

**Related (canonical today):**

- [`docs/pipeline/POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md) — manual post-send loop
- [`docs/CRUD_SAFETY.md`](../CRUD_SAFETY.md) — mutation policy
- [`docs/SCRIPT_MAP.md`](../SCRIPT_MAP.md) — break-glass vs daily tools
- [`src/origenlab_email_pipeline/qa/ndr_review_queue.py`](../../src/origenlab_email_pipeline/qa/ndr_review_queue.py) — batch A–E classification + allowlists
- [`scripts/tools/flag_ndr_bounces_from_contacto.py`](../../scripts/tools/flag_ndr_bounces_from_contacto.py) — NDR scan + targeted apply

---

## 1. Current manual NDR loop

After outbound mail or new INBOX NDRs, operators follow the post-send safe loop. NDR-specific steps:

| Step | Command | Writes SQLite? |
|------|---------|----------------|
| 1. Gmail ingest | `05_workspace_gmail_imap_to_sqlite.py` (INBOX + Sent) | Yes (emails) |
| 2. NDR dry-run | `flag_ndr_bounces_from_contacto.py --since-days N` | **No** |
| 3. Human-review batches | `uv run origenlab ndr-review -- --since-days N` | **No** — writes `reports/out/active/current/ndr_review_queue_<date>/` |
| 4. Operator review | Read `NDR_REVIEW_SUMMARY.md`, batch CSVs, `DO_NOT_APPLY_WITHOUT_APPROVAL.md` | — |
| 5. Targeted apply (A or B only, when approved) | `flag_ndr_bounces_from_contacto.py --emails-file …/apply_allowlist_batch_a.txt --only-code bounce_no_such_user --apply` | **Yes** — `contact_email_suppression` per exact email |
| 6. Contacted universe audit | `audit_contacted_universe.py` | **No** |
| 7. Safety memory | `uv run origenlab refresh-safety` | **No** (exports to `reports/out`) |
| 8. Post-send digest | `uv run origenlab post-send-digest -- --since-days N` | **No** |
| 9. Postgres mirror | `auto-mirror-dashboard` / `mirror-dashboard --live --apply` | Postgres mirror only |

### Batch model (already implemented)

`ndr-review` classifies each NDR candidate into human-review queues:

| Batch | Meaning | `--only-code` for targeted apply | Auto-apply candidate? |
|-------|---------|----------------------------------|------------------------|
| **A** | Clear no-such-user / mailbox unavailable with strong body evidence | `bounce_no_such_user` | **Stage 2** (future) |
| **B** | Clear NXDOMAIN / domain-not-found | `bounce_other` | **Stage 3** (future, gated) |
| **C** | Quota / mailbox-full | — | **Never** |
| **D** | Policy / access / spam blocks | — | **Never** |
| **E** | Parser uncertainty, delay DSN, multi-recipient, unmapped codes | — | **Never** |

Suggested allowlists (`apply_allowlist_batch_a.txt`, `apply_allowlist_batch_b.txt`) contain **unsuppressed** emails only. They are **suggestions** — operator must explicitly approve before any `--apply`.

### Apply guards (already in `flag_ndr_bounces_from_contacto.py`)

- Default is **dry-run** (no writes).
- **Broad `--apply`** without `--emails-file` and `--only-code` upserts all scan matches — **break-glass / forbidden** for automation.
- Targeted apply requires each allowlist email to appear in the **current** NDR scan evidence; otherwise `refused_not_in_ndr_evidence` and exit code 1.
- `--only-code` mismatch → `refused_wrong_code` and exit code 1.
- **Exact-email only** — never domain suppression from NDR.
- `manual_do_not_contact` rows are skipped, not overwritten.
- Delay DSN subjects are excluded at scan time.

---

## 2. Evidence from 2026-06-11 (manual run)

Operator ran the manual loop after a recent outbound wave. On-disk artifacts under `reports/out/active/current/`:

### NDR dry-run + review queue

`ndr_review_queue_2026_06_11/` (`ndr_review_summary.json`, generated `2026-06-11T21:43:08+00:00`, `since_days: 1`):

| Metric | Value |
|--------|------:|
| Scanned rows | 157 |
| Planned distinct recipients | 129 |
| Already suppressed | 53 |
| Unsuppressed candidates | 76 |
| Batch A (no-such-user) | 53 |
| Batch B (NXDOMAIN) | 28 |
| Batch C (quota) | 1 |
| Batch D (policy) | 42 |
| Batch E (uncertain) | 5 |
| Suggested allowlist A | 18 emails |
| Suggested allowlist B | 14 emails |

### Targeted A + B apply (operator-reported)

Manual targeted applies used the generated allowlist files with:

- `refused_not_in_ndr_evidence=0`
- `refused_wrong_code=0`

All allowlist emails matched current scan evidence and expected suppression codes.

### Post-apply safety chain

| Check | Outcome |
|-------|---------|
| `refresh-safety` | Passed (exports refreshed; `do_not_repeat_summary.json` `generated_at` `2026-06-11T21:44:57Z`, `from_email_suppression: 295`) |
| `audit_contacted_universe` | `contacted_universe_summary.json`: **Bounced emails = 211**, **Suppressed contacts = 295** |
| Dashboard Postgres mirror | Mirror log reported **`email_suppressions: 295`** aligned with SQLite sidecar count |

**Conclusion:** Targeted Batch A + B apply with existing guards worked cleanly today. Automation should **reuse** `flag_ndr_bounces_from_contacto.py` selection logic — not reimplement suppression writes.

---

## 3. Proposed staged automation

**Principle:** Ship visibility before writes. Each stage is independently mergeable and **off by default** until explicitly invoked.

### Stage 1 — Status-only “NDR pending review” (no apply)

**Goal:** Surface actionable NDR backlog in operator status and dashboard without mutating SQLite.

**Behavior:**

- After `ndr-review` (or an equivalent read-only scan), expose in `operator-automation-status` / dashboard snapshot:
  - `ndr_pending_review: true|false`
  - `ndr_review_queue_date_label` (e.g. `2026_06_11`)
  - `ndr_unsuppressed_batch_a_count`, `ndr_unsuppressed_batch_b_count`
  - `ndr_batch_cde_count` (C+D+E combined — informational hold)
  - `ndr_since_days` used for last scan
  - `ndr_generated_at_utc`
- Derive from latest `ndr_review_queue_*` summary JSON or lightweight re-scan (read-only).
- **No `--apply`**, no cron auto-apply.

**Operator UX (dashboard Sistema / health):** e.g. “NDR pendiente de revisión: 18 Batch A, 14 Batch B (desde cola 2026-06-11)”.

### Stage 2 — Auto-apply Batch A only (strict guards, opt-in CLI)

**Goal:** Automate **only** Batch A (`bounce_no_such_user`) when all guards pass.

**Invocation (future, not enabled today):**

```bash
uv run origenlab ndr-safe-auto-apply --batch A --dry-run
uv run origenlab ndr-safe-auto-apply --batch A --apply --operator rafael
```

**Flow:**

1. Run read-only NDR scan + batch classification (same as `ndr-review`).
2. Build allowlist = Batch A unsuppressed emails (same rules as today).
3. **Dry-run default:** print planned applies + audit preview; exit 0.
4. **`--apply` path:** delegate to existing targeted apply in `flag_ndr_bounces_from_contacto.py` (subprocess or shared module) with:
   - `--emails-file` (temp allowlist)
   - `--only-code bounce_no_such_user`
   - **Never** broad `--apply`
5. Post-apply: run `refresh-safety` (real run in prod; mocked in tests).
6. Write audit JSON/JSONL under `reports/out/active/current/ndr_safe_auto_apply_<timestamp>/`.
7. **Do not send mail.**

**Hard refusals (exit non-zero, no writes):**

- `--batch B|C|D|E` with `--apply` in Stage 2 (B not enabled yet; C/D/E never).
- Missing `--operator` on `--apply`.
- Batch E count above threshold (see guardrails).
- Any `refused_not_in_ndr_evidence` or `refused_wrong_code` from underlying tool.
- Empty allowlist.

### Stage 3 — Optional Batch B auto-apply (gated, manual enable)

**Goal:** Allow `bounce_other` NXDOMAIN batch **only after** multiple clean reviewed campaigns.

**Extra gates (all required):**

- Feature flag file or config: `ndr_safe_auto_apply_batch_b_enabled` (default **false**).
- Minimum **N** prior Batch A auto-apply runs with audit logs showing `refused_*=0` and `refresh-safety` success (suggest N=3).
- Per-run **max count** lower than Batch A (NXDOMAIN misclassification risk).
- Operator `--reason` required on `--apply`.
- Still **never** C/D/E.

**Not in scope for initial implementation** — design hook only.

### Never auto-apply

| Batch | Reason |
|-------|--------|
| **C** | Transient quota — may recover |
| **D** | Policy/spam — wrong to treat as permanent hard bounce |
| **E** | Parser uncertainty — human must decide |
| **Broad apply** | Break-glass; all scan matches |

---

## 4. Guardrails (all stages)

| Guardrail | Detail |
|-----------|--------|
| **Default dry-run** | No `--apply` → no SQLite writes |
| **No broad `--apply`** | CLI must refuse `--apply` without `--batch` and without internal allowlist construction |
| **Require current NDR evidence** | Reuse `select_planned_for_apply`; refuse emails not in live scan |
| **Require `--only-code`** | Batch A → `bounce_no_such_user`; Batch B → `bounce_other` only in Stage 3 |
| **Exact email only** | `contact_email_suppression` per address; **no** domain suppression |
| **Max auto-apply per run** | Configurable cap (suggest: A ≤ 25, B ≤ 10 when enabled); refuse overflow for human review |
| **Parser uncertainty threshold** | Refuse auto-apply if Batch E unsuppressed count > 0 in same `since_days` window (or > fixed threshold, e.g. 3) |
| **Audit log** | JSON summary + JSONL per email: `{email, code, batch, email_id, date_iso, action, refused_reason?}` |
| **`--operator` + `--reason` on apply** | Required for `--apply`; stored in audit and `updated_by` |
| **`refresh-safety` after apply** | Mandatory post-step; failure → audit marks `post_apply_refresh_safety_ok: false` |
| **No mail send** | Command must not invoke Gmail send, drafts, or outreach queue builders |
| **No Postgres migrations** | Mirror refresh remains separate operator step |
| **Respect `manual_do_not_contact`** | Inherited from underlying apply tool |
| **Pause file** | Future: `reports/out/active/current/ndr_safe_auto_apply_paused` skips `--apply` (mirrors mail/mirror pause pattern) |

### Proposed audit layout

```
reports/out/active/current/ndr_safe_auto_apply_<UTC compact>/
  audit_summary.json      # counts, refused_*, batch, operator, refresh_safety_rc
  audit_events.jsonl      # one line per email decision
  allowlist_applied.txt     # copy of emails passed to --emails-file
```

---

## 5. Suggested future command surface

New unified operator subcommand (name tentative, not registered yet):

```bash
# Preview Batch A allowlist + guards (default)
uv run origenlab ndr-safe-auto-apply --batch A --dry-run

# Apply Batch A after guards (explicit operator)
uv run origenlab ndr-safe-auto-apply --batch A --apply --operator rafael --reason post_campaign_ndr_batch_a

# Common flags
--since-days 1          # match ndr-review window (default: 1)
--max-apply 25          # cap per run
--queue-dir PATH        # optional: reuse existing ndr_review_queue_* instead of rescanning
```

**Refuse examples:**

```bash
uv run origenlab ndr-safe-auto-apply --batch E --apply   # → exit 1, never
uv run origenlab ndr-safe-auto-apply --apply             # → exit 1, missing --batch
uv run origenlab ndr-safe-auto-apply --batch A --apply   # → exit 1, missing --operator
```

Implementation should **wrap** existing tools, not fork suppression semantics:

- Classification: `build_ndr_review_queue` / `classify_ndr_candidate`
- Apply: `flag_ndr_bounces_from_contacto.py` targeted mode
- Post-apply: `refresh-safety` subprocess

---

## 6. Tests required (before any `--apply` is enabled in CI/prod)

All tests use **temp SQLite** fixtures; **mock** `refresh-safety` subprocess (do not run real safety chain in unit tests).

| Test | Assert |
|------|--------|
| `test_refuses_batch_d_and_e_apply` | `--batch D --apply` and `--batch E --apply` exit non-zero, zero suppression writes |
| `test_refuses_broad_apply` | `--apply` without `--batch` refused; no call path that omits `--emails-file` + `--only-code` |
| `test_applies_only_batch_a` | Batch A allowlist emails get `contact_email_suppression`; Batch B/C/D/E emails in fixture do not |
| `test_refuses_email_not_in_ndr_evidence` | Inject email not in scan → `refused_not_in_ndr_evidence` > 0, exit 1, no writes |
| `test_refuses_wrong_code` | Email in evidence with `bounce_other` cannot apply under Batch A `--only-code bounce_no_such_user` |
| `test_writes_audit_log` | `--dry-run` and `--apply` both write `audit_summary.json` + `audit_events.jsonl` with expected schema |
| `test_refresh_safety_invoked_after_apply` | Mock subprocess: assert called exactly once on successful `--apply`; not called on dry-run |
| `test_refuses_when_batch_e_above_threshold` | Fixture with unsuppressed E > threshold → refuse apply |
| `test_max_apply_cap` | Allowlist 30, `--max-apply 25` → only 25 applied (or refuse — pick one behavior and lock in tests) |
| `test_stage1_status_fields` | `operator-automation-status` includes `ndr_pending_review` counts from latest queue dir |

**Regression fixtures:** Use real batch-reason patterns from `test_ndr_review_queue.py` (A no-such-user, B nxdomain, C quota, D policy, E uncertain).

---

## 7. Exact next PR steps (recommended order)

Each PR is small, reviewable, and **does not enable unattended cron apply** until the final operator decision.

### PR 1 — Design doc only (this document)

- **Files:** `docs/design/NDR_SAFE_AUTO_APPLY_PLAN.md`
- **Behavior:** None
- **Tests:** None (docs-only)
- **Merge gate:** Operator review of batch policy and guardrails

### PR 2 — Stage 1: NDR pending review in operator status

- **Scope:** Read-only aggregation from latest `ndr_review_queue_*` summary (or call `build_ndr_review_queue` in dry mode)
- **Files (likely):**
  - `src/origenlab_email_pipeline/operator_cli/operator_automation_status.py`
  - `src/origenlab_email_pipeline/qa/ndr_pending_review_status.py` (new small module)
  - `tests/test_ndr_pending_review_status.py`
  - `docs/pipeline/POST_SEND_SAFE_LOOP.md` (link to this plan)
- **API/dashboard:** Optional follow-up PR in `apps/api` + `apps/dashboard` to display fields (read-only)
- **Tests:** Fixture queue dir → status JSON includes counts; no SQLite writes

### PR 3 — `ndr-safe-auto-apply` skeleton (dry-run only)

- **Scope:** CLI registration + `--batch A --dry-run` only; prints allowlist + guard evaluation; writes audit preview
- **Files (likely):**
  - `src/origenlab_email_pipeline/operator_cli/ndr_safe_auto_apply.py` (new)
  - `src/origenlab_email_pipeline/operator_cli/parser.py` / `constants.py`
  - `tests/test_ndr_safe_auto_apply.py`
- **No `--apply` yet** — subprocess to `flag_ndr_bounces` mocked/not called for writes

### PR 4 — Batch A `--apply` path + audit + refresh-safety hook

- **Scope:** Enable `--apply --operator` for Batch A only; full audit JSON/JSONL; post-apply `refresh-safety` (subprocess)
- **Tests:** Full matrix from §6; mock refresh-safety
- **Docs:** Update `OPERATOR_COMMAND_SURFACE.md`, `SCRIPT_MAP.md` (break-glass note: still not cron-scheduled)

### PR 5 — Dashboard + API exposure (optional)

- **Scope:** Show `ndr_pending_review` and last audit timestamp on Sistema tab
- **Safety:** Read-only UI; no apply button in dashboard v1 freeze

### PR 6 — Stage 3 Batch B (deferred)

- **Scope:** Feature flag + extra gates + separate operator runbook section
- **Only after** 3+ clean Batch A audited runs in production

### Explicitly out of scope

- Cron scheduling of `ndr-safe-auto-apply --apply`
- Broad NDR `--apply`
- Domain-level suppression from NDR
- Auto-apply C/D/E
- Gmail send integration

---

## 8. Open questions (operator decision before PR 3)

1. **Max apply cap behavior:** Refuse entire run if allowlist > cap, or apply first N and leave remainder for manual review?
2. **Batch E threshold:** Refuse when *any* unsuppressed E exists, or only when E count > 3?
3. **Reuse queue dir vs rescan:** Prefer fresh scan on every auto-apply invocation, or trust same-day `ndr_review_queue_*` artifact?
4. **Pause file:** Add `ndr_safe_auto_apply_paused` in PR 4 or defer?

---

## 9. Safety reminder

NDR suppression affects **send gates** (`contact_email_suppression`). A wrong apply blocks future outreach to a live buyer. This plan intentionally limits automation to Batch A (clear hard bounces) and defers Batch B until repeated manual validation proves the pipeline.

**Until Stage 2 is explicitly approved and merged, operators must continue the manual loop in [`POST_SEND_SAFE_LOOP.md`](../pipeline/POST_SEND_SAFE_LOOP.md).**
