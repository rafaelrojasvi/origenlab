# First reduction wave — closing note (2026-06-07)

**Status:** wave closed (PR #127)  
**Scope:** `apps/email-pipeline` — docs/tests only  
**Companion:** [`REDUCTION_SHORTLIST_20260607.md`](REDUCTION_SHORTLIST_20260607.md) (candidate inventory; not reopened by default)

---

## Purpose

This note closes the **first reduction wave** started in PR #120. It records what was completed, what boundaries were preserved, and when future work may revisit these items. It is **not** a new planning doc and does **not** add new reduction candidates.

---

## Completed wave (#117–#126)

| PR | Target | Safe default |
|----|--------|--------------|
| **#117** | Stale reduction references | Removed live-operator mentions of deleted paths; guarded by `test_stale_reduction_references.py` |
| **#118** | `prepare_active_workspace.py` | Plan-only by default; **`--apply`** required to move/write under `reports/out/active/` |
| **#119** | `build_archive_send_batch.py` | Audit-only by default; **`--build-batch`** required for send_ready/review CSVs |
| **#121** | Tatiana / dataset / ml / campaigns | Lab boundary clarified in [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md) — not daily outbound |
| **#122** | `export_marketing_from_contact_master.py` | Audit-only by default; **`--export`** + **`--out`** required to write CSVs |
| **#123** | `apply_ready8_contact_patch.py` | Plan-only by default; **`--apply`** required to write hunt/top20/plan files |
| **#124** | Zero-ref advanced helpers | Owner-review documented for `export_leads_spanish_csvs.py` and `run_contact_hunt_web_server.py` |
| **#125** | `export_leads_spanish_csvs.py` | Plan-only by default; **`--write-outputs`** required to write Spanish `_es` CSVs |
| **#126** | `run_contact_hunt_web_server.py` | Localhost-only default (**127.0.0.1**); **`--lan`** for LAN; password required |

PR #120 created the shortlist; PRs #118–#126 implemented the scoped runtime gates and doc passes listed above.

---

## Safe-default changes (summary)

- **Apply gates:** `--apply` required before writes (`prepare_active_workspace`, `apply_ready8_contact_patch`).
- **Audit-only defaults:** read/plan output unless explicit write flags (`build_archive_send_batch`, `export_marketing_from_contact_master`).
- **Explicit write flags:** `--write-outputs` (Spanish CSV helper), `--build-batch` (archive batch).
- **Network/auth hardening:** localhost bind by default; **`--lan`** for intentional LAN exposure; no default web password.

---

## Boundaries preserved

This wave did **not** change:

- Gmail ingest
- Send / purge paths
- NDR suppression **apply**
- Postgres mirror / Alembic migrations
- Outbound gate / safety modules (`candidate_export_gate`, `outbound_core`, `outreach_contact_state`, `csv_contracts`, etc.)
- Daily-core runtime (`origenlab daily-core`, `refresh-dashboard`)

---

## Do not reopen unless regression

Do **not** re-open completed candidates (#118–#126) unless:

- Relevant tests fail
- Docs drift from implemented defaults
- A script **regresses** to write or expose by default without an explicit flag
- An owner explicitly asks to retire or delete a reviewed helper

When reopening, cite the regression (test name, PR, or observed behavior) — not planner zero-ref counts alone.

---

## What comes after this wave

**Stop this reduction wave.** The first wave targeted script safety gates and lab/parked boundaries for known candidates.

The **next wave** should focus on function-level consolidation or product/operator UX work — **not** more script safety gates by default. Residual shortlist rows (e.g. `export_all_known_marketing_contacts.py` doc clarification) are optional, small follow-ups — not a continuation of this wave.

---

## Related docs and tests

- [`REDUCTION_SHORTLIST_20260607.md`](REDUCTION_SHORTLIST_20260607.md) — candidate table (frozen for this wave)
- [`SCRIPT_MAP.md`](../SCRIPT_MAP.md) — canonical script classification
- [`test_reduction_wave_summary_docs.py`](../../tests/test_reduction_wave_summary_docs.py) — locks this closing note
- [`test_reduction_shortlist_docs.py`](../../tests/test_reduction_shortlist_docs.py) — locks shortlist guardrails
