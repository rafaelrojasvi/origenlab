# Contacted universe and no-repeat prospecting (Phase 10A)

Before running new **DeepSearch** prospecting, operators need a single read-only view of who OrigenLab has already touched via `contacto@origenlab.cl`, who bounced, and which domains are blocked.

**Source of truth:** SQLite (`emails`, suppressions, outreach sidecar).  
**Not used for send decisions alone:** Postgres/dashboard mirrors (read-only reporting).

## Quick start

```bash
cd apps/email-pipeline
uv run python scripts/leads/audit_contacted_universe.py
```

Default outputs (under `reports/out/active/current/`):

### Raw safety universe (unchanged — full mail graph)

| File | Purpose |
|------|---------|
| `contacted_universe_summary.json` | Counts for dashboards / automation |
| `contacted_universe_summary.md` | Human-readable summary (raw vs clean sections) |
| `contacted_universe_contacts.csv` | One row per known contact email (~28k+ rows) |
| `contacted_universe_domains.csv` | Aggregated by registrable domain |

### Clean exports for DeepSearch / prospecting (Phase 10A.1)

| File | Purpose |
|------|---------|
| `contacted_exact_emails_for_exclusion.csv` | Emails OrigenLab already touched or must not re-mail |
| `contacted_domains_for_exclusion.csv` | Domains with Sent, bounce, supplier, or suppression |
| `bounced_emails_for_exclusion.csv` | Bounce suppressions only |
| `suppressed_contacts_for_exclusion.csv` | Email-level suppressions |
| `follow_up_candidates_review.csv` | Human shortlist for realistic follow-up |
| `noisy_contacts_review.csv` | Why the raw universe is huge (noreply, marketplaces, etc.) |

Optional: point at a specific DB or merge `do_not_repeat_master.csv`:

```bash
uv run python scripts/leads/audit_contacted_universe.py \
  --db /path/to/emails.sqlite \
  --do-not-repeat-csv reports/out/active/current/do_not_repeat_master.csv
```

## What counts as “already contacted”

Priority signals (same as cold-export gate):

1. **Gmail Sent** — `emails.recipients` on `contacto@origenlab.cl` in `[Gmail]/Enviados` / `[Gmail]/Sent Mail`
2. **`outreach_contact_state`** — `contacted`, `replied`, `snoozed`
3. **`contact_email_suppression`** — bounces (mailer-daemon / NDR) and manual blocks
4. **`contact_domain_suppression`** — whole-domain blocks
5. **`supplier_master`** — supplier domains (do not cold-market)
6. **`do_not_repeat_master.csv`** — merged export from `export_do_not_repeat_master.py` when present

## Contact CSV columns

`normalized_email`, `domain`, `display_name`, `organization_name`, `first_contacted_at`, `last_contacted_at`, `sent_count`, `received_count`, `replied_bool`, `bounced_bool`, `suppressed_bool`, `outreach_state`, `role_guess`, `buyer_type_guess`, `product_interest_guess`, `latest_subject_safe`, `recommended_status`, `reason_codes`

### `recommended_status` (contact)

| Value | Meaning |
|-------|---------|
| `already_contacted` | In Sent history and/or outreach `contacted` / DNR list |
| `follow_up_candidate` | Replied or two-way thread (inbound after outbound) |
| `bounced_do_not_contact` | Bounce suppression |
| `supplier_do_not_market` | Known supplier domain |
| `internal_do_not_market` | `@origenlab.cl` / internal blocklist |
| `unknown_review` | In graph but unclear for cold outreach |

## Domain CSV columns

`domain`, `organization_name`, `sent_count`, `received_count`, `unique_contacts`, `bounced_count`, `suppressed_bool`, `supplier_bool`, `internal_bool`, `buyer_type_guess`, `latest_contacted_at`, `recommended_status`, `reason_codes`

## When to use which export

| Task | File |
|------|------|
| Block DeepSearch / import duplicates | `contacted_exact_emails_for_exclusion.csv` + `contacted_domains_for_exclusion.csv` |
| Never mail again (bounce) | `bounced_emails_for_exclusion.csv` |
| Operator suppression list | `suppressed_contacts_for_exclusion.csv` |
| Tatiana follow-up queue | `follow_up_candidates_review.csv` |
| Audit noise in archive | `noisy_contacts_review.csv` |
| Forensics / safety overrides | Raw `contacted_universe_*.csv` |

**Exact email exclusion** includes only rows with Sent history, outreach `contacted`/`snoozed`/`replied`, bounce, or suppression — not every `contact_master` row from inbound spam.

**Noisy review** flags noreply/unsubscribe locals, mailer-daemon, numeric locals, supplier marketplace domains (`verifiedsupplier`, `chinalabsupplies`, `chromatography.ltd`, …), suspicious random domains, and context-free freemail.

## Net-new eligibility (for DeepSearch candidates)

Use `classify_net_new_eligibility(email, domain, ctx=...)` from `origenlab_email_pipeline.leads.contacted_universe_audit`:

| Result | Meaning |
|--------|---------|
| `net_new_safe` | No blockers — OK to research / queue |
| `already_contacted` | Sent or outreach state |
| `same_domain_contacted_review` | Domain has other contacted mailboxes |
| `bounced_block` | Bounce suppression |
| `suppressed_block` | Email or domain suppression |
| `supplier_block` | Supplier domain |
| `internal_block` | Internal / operator domain |
| `invalid_or_noise` | Unparseable or noise heuristics |

**Suppression always wins** over “never emailed” assumptions.

## Safety rules (audit output)

The audit does **not** write:

- Raw email bodies
- Gmail URLs
- Bank / RUT fields
- `source_file` paths
- Attachment / transfer / operation IDs

`latest_subject_safe` is truncated subject text only.

## Related scripts

| Script | Role |
|--------|------|
| `scripts/qa/export_do_not_repeat_master.py` | Unified DNR CSV |
| `scripts/qa/export_outreach_contacted_all.py` | Simple contacted email list |
| `scripts/qa/refresh_outbound_safety_memory.py` | Refresh DNR + validators |
| `scripts/leads/export_next_marketing_recipients.py` | Ranked next sends (gate-aware) |
| `scripts/qa/export_contacted_lead_overlap_audit.py` | Lead/research overlap vs Sent |

## Tests

```bash
cd apps/email-pipeline
uv run pytest tests/test_audit_contacted_universe.py -q
```

## Implementation

- Module: `src/origenlab_email_pipeline/leads/contacted_universe_audit.py`
- CLI: `scripts/leads/audit_contacted_universe.py`
- Reuses: `marketing_export_context`, `candidate_export_gate`, `marketing_supplier_domains`
