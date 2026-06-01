# Institution Explorer — product / read-model spec

Status: canonical (spec only — not implemented)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-01

Related: [`INSTITUTION_ALIAS_POLICY.md`](INSTITUTION_ALIAS_POLICY.md) · [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md) · [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md) · [`../scripts/qa/audit_institution_grouping.py`](../scripts/qa/audit_institution_grouping.py)

**This document is a spec.** It does not authorize schema changes, UI implementation, or send-path coupling.

---

## 1. Purpose

The **Institution Explorer** is a **read-only operator view** of organizations and domains derived from the business mart and safety sidecars.

It helps operators:

- Understand **contact history** per domain (sent, received, replies, bounces).
- See **sector / classification guesses** and confidence from audit heuristics.
- Spot **suppressions**, **outreach state**, and **supplier/vendor** domains before planning research or exports elsewhere.
- Review **proposed alias groupings** (display-only) when approved in the future.

It is **not** a send surface. Export and send decisions remain on suppression sidecars, outreach state, export gates, and Sent preflight — never on institution cards or alias display.

---

## 2. Non-goals

| Non-goal | Rationale |
| --- | --- |
| **Sending email** | Explorer is GET-only; no compose, draft, or queue actions. |
| **Contact mutation** | No edit contact, merge contact, or rewrite mart rows from the UI. |
| **Gmail mutation** | No archive, label, or delete from explorer. |
| **Automatic alias merge** | No production `institution_alias` table yet; no silent contact roll-up. |
| **Suppression bypass** | Cards may *show* suppression state; they must not *clear* or override it. |
| **Institution-based send approval** | `classification_guess`, `sector_guess`, or alias grouping must not gate cold export. |
| **Operational SoT** | Explorer read model is rebuildable; SQLite sidecars remain authoritative for safety. |

---

## 3. Card model (domain-primary)

**Primary key:** registrable **domain** (from `contact_master.domain` / `organization_master.domain`).

Each **institution / domain card** exposes the following fields (API or CSV-equivalent):

| Field | Source / notes |
| --- | --- |
| `display_name` | `organization_master.organization_name_guess` or dominant `contact_master.organization_name_guess`; fallback = domain |
| `primary_domain` | Registrable domain string |
| `aliases` | Org-name variants on same domain (`org_name_variants` from audit inventory) |
| `proposed_aliases` | Optional future: approved alias canonical name + grouped domains — **display only**, from signed-off seed list |
| `sector_guess` | Audit heuristic (`likely_sector` in `domain_org_inventory.csv`) |
| `confidence` | `high` \| `medium` \| `low` \| `needs_review` — from grouping audit |
| `promotion_bucket` | e.g. `unknown_review`, `supplier_vendor`, `platform_or_marketing`, … |
| `do_not_promote_to_institution` | Boolean — audit flag for noise/platform domains |
| `contact_count` | Distinct emails on domain in `contact_master` |
| `generic_mailbox_count` | Contacts with generic locals (`contacto@`, `ventas@`, …) |
| `sent_count` | Sum `outbound_emails` on domain |
| `received_count` | Sum `inbound_emails` on domain |
| `reply_count` | Inbound count used as reply proxy (same as audit today) |
| `bounce_count` | Contacts with bounce suppression on domain |
| `exact_suppression_count` | Rows in `contact_email_suppression` for emails on domain |
| `domain_suppression_state` | `none` \| `blocked` if domain in `contact_domain_suppression` |
| `contacted_state_summary` | Counts by `outreach_contact_state` (`contacted`, `replied`, `snoozed`, …) |
| `supplier_vendor_warning` | True if `supplier_master` / domain suppression / mart supplier heuristic |
| `last_contact_date` | Max `last_seen_at` from contacts on domain |
| `active_case_indicators` | Optional: warm-case or contacted-domain flags when mirrored |
| `source_tables` | Evidence summary, e.g. `contact_master;organization_master;outreach_contact_state` |
| `review_reason` | Semicolon-separated flags from audit (`low_confidence_domain`, `do_not_promote`, …) |

**Grouping rule (v1):** one card per domain. Optional visual grouping under an approved alias is Phase 3 only.

---

## 4. Safety banners

Every explorer list page, detail page, and export preview must show:

> **Read-only. Not a send surface. Send gates remain suppression/outreach sidecars.**

Secondary line (Spanish operator UI, when localized):

> **Solo lectura. No es una pantalla de envío. La seguridad de envío sigue en supresión y estado de contacto.**

Cards with `domain_suppression_state=blocked` or any `exact_suppression_count > 0` should show a **safety badge** (informational, not actionable).

---

## 5. Filters

Explorer list supports read-only filters (all optional, combinable):

| Filter | Behavior |
| --- | --- |
| **sector** | `sector_guess` from audit taxonomy |
| **contacted / not contacted** | Any contact on domain in `outreach_contact_state` contacted/replied/snoozed vs none |
| **suppressed** | `exact_suppression_count > 0` or domain suppressed |
| **bounced** | `bounce_count > 0` |
| **supplier / vendor** | `supplier_vendor_warning=true` |
| **generic mailbox heavy** | `generic_mailbox_count / contact_count` above threshold (e.g. ≥50%) |
| **high confidence** | `confidence=high` and `do_not_promote_to_institution=false` |
| **needs review** | `confidence` in (`low`, `needs_review`, `medium`) or non-empty `review_reason` |
| **do_not_promote_to_institution** | Audit noise/platform flag — default **exclude** from “prospect institution” preset |

Preset: **“Buyer institutions (explorer)”** = not supplier, not `do_not_promote`, confidence ≥ medium.

---

## 6. Data sources

| Layer | Store / artifact | Role in explorer |
| --- | --- | --- |
| Evidence | `contact_master` | Per-email counts, org guesses, last seen |
| Evidence | `organization_master` | Domain-level org name/type aggregates |
| Evidence | `emails` (aggregates) | Optional future: thread/topic summaries — not v1 |
| Safety | `contact_email_suppression` | Exact-email block counts |
| Safety | `contact_domain_suppression` | Domain block state |
| Lifecycle | `outreach_contact_state` | Contacted / snoozed summary |
| Safety | Export gates / Sent preflight | **Not displayed as approval** — link out to existing export QA only |
| Classification | `institution_grouping_audit` outputs | `domain_org_inventory.csv`, `institution_candidates.csv`, summary JSON |
| Vendor | `supplier_master`, supplier heuristics | `supplier_vendor_warning` |
| Aliases (future) | Signed-off seed CSV / proposed table | `proposed_aliases` display only — see [`INSTITUTION_ALIAS_POLICY.md`](INSTITUTION_ALIAS_POLICY.md) |

Rebuild path: run `audit_institution_grouping.py` after mart rebuild; mirror to Postgres only when API Phase 1 exists.

---

## 7. Suggested API / read model (fields only — not implemented)

All routes **GET-only**. Served from SQLite mirror or Postgres read replica — never write-back.

### `GET /mirror/institution_cards` (list)

Query params: filters from §5, `limit`, `offset`, `sort` (`sent_count`, `last_contact_date`, `display_name`).

Response item: card model fields from §3 (subset for list).

### `GET /mirror/institution_cards/{domain}` (detail)

Full card model + nested summaries below.

### `institution_contact_summary` (embedded or sub-resource)

| Field | Description |
| --- | --- |
| `domain` | Primary domain |
| `contacts[]` | `{ email, contact_name_best, generic_mailbox, outbound, inbound, suppression_state, outreach_state }` |
| `generic_mailbox_contacts[]` | Subset flagged generic |

### `institution_email_history_summary` (embedded)

| Field | Description |
| --- | --- |
| `domain` | Primary domain |
| `first_seen_at` | Min contact first seen |
| `last_seen_at` | Max contact last seen |
| `sent_count` / `received_count` / `reply_count` | Domain totals |
| `note` | “Detailed thread view deferred; use mail tools elsewhere.” |

### `institution_safety_summary` (embedded)

| Field | Description |
| --- | --- |
| `domain` | Primary domain |
| `domain_suppressed` | bool |
| `suppressed_emails[]` | `{ email, reason_code }` — read-only |
| `contacted_emails_count` | From outreach sidecar |
| `send_gate_reminder` | Static string: sidecars authoritative |

**No** `POST`, `PATCH`, or `DELETE` on institution routes.

---

## 8. UI states (card presentation)

| State | Visual treatment | Operator meaning |
| --- | --- | --- |
| **safe_read_only_domain** | Default card; confidence badge | Normal explorer card |
| **suppressed_domain** | Red/amber safety stripe | Domain or emails blocked — do not cold-export from this view |
| **supplier_vendor** | Distinct icon + “Proveedor” label | Not a buyer institution KPI |
| **ambiguous_alias** | Dashed group border | Multiple org names or proposed alias — no auto-merge |
| **generic_mailbox_only** | Muted person icon | Route by domain; mailboxes not persons |
| **no_email_contact** | Empty state | Domain in mart with zero contacts — rare |
| **needs_business_review** | “Revisar” badge | Conglomerate, bank, or low-confidence cluster |

---

## 9. Future alias handling

Per [`INSTITUTION_ALIAS_POLICY.md`](INSTITUTION_ALIAS_POLICY.md):

| Alias status | Explorer behavior |
| --- | --- |
| **Proposed** (`proposed_manual_review`) | Show badge “alias propuesto”; do not group cards |
| **Approved** (manual sign-off) | Visual group under `display_name`; each domain card remains addressable |
| **Rejected** | Hidden from alias grouping |

Rules:

- Aliases **group cards visually only** — no merged contact rows.
- **Never** feed `candidate_export_gate`, NDR apply, or outreach writes.
- Approved alias list is a **small, versioned artifact** — not auto-synced from latest audit CSV without operator review.

---

## 10. Rollout plan

| Phase | Scope | Send coupling |
| --- | --- | --- |
| **0 — now** | Manual use of audit CSVs under `reports/out/active/current/institution_grouping_audit_*` | None |
| **1** | Read-only API: `institution_cards` list + detail by domain (mirror) | None |
| **2** | Dashboard explorer page: filters, safety banner, detail drawer | None |
| **3** | Optional approved-alias visual grouping | Display only |
| **Never** | Send, draft, export approve, suppression edit from explorer | **Forbidden** |

Exit criteria for Phase 1:

- [ ] Golden send-gate rule unchanged in tests/docs
- [ ] API routes registered as GET-only
- [ ] Card fields match audit inventory column semantics
- [ ] Supplier and `do_not_promote` domains clearly badged

---

## Appendix: audit command

```bash
uv run python scripts/qa/audit_institution_grouping.py --date-label YYYY_MM_DD
```

Output folder (gitignored): `reports/out/active/current/institution_grouping_audit_<YYYY_MM_DD>/`
