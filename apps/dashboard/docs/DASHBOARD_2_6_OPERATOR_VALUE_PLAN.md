# Dashboard-2.6 — Operator value improvements (plan)

**Status:** planning (no implementation in this doc)  
**Date:** 2026-05-22  
**Scope:** Read-only Today page (`apps/dashboard` :5173 → `apps/api` :8001 GET only). No write actions, Gmail mutation, SQLite/Postgres/CSV mutation, or new send approval semantics.

**Baseline:** Dashboard v1 freeze + Dashboard-2 contact drilldown + 2.3 table polish + 2.5 operator usability ([V1_FREEZE_OPERATOR_HANDOFF.md](./V1_FREEZE_OPERATOR_HANDOFF.md)).

---

## Current Today surface (review)

| Area | What exists | Gaps for operators |
|------|-------------|-------------------|
| **Operator status** | Verdict banner, campaign/focus, outbound readiness note, warnings (max **5** preview + “+N more”) | Warnings are flat strings; no expand; no structured severity; readiness vs mirror truth easy to misread |
| **Warm cases** | `GET /cases/warm` (default client: `days=14`, `limit=30`, `positive_signal_only=false`); search/status/category sort; hide internal contacts | API default sort = last_seen desc; no “needs reply” preset; `gmail_url` returned by API but **stripped in UI parser**; `include_noise` / `days` not exposed; cap not obvious when `meta.count` > loaded rows |
| **Equipment** | `GET /opportunities/equipment` (`limit=30`); search + rank/close-date sort | API supports `priority`, `next_action`, `safe_channel`, `include_account_intelligence` — **not exposed in UI**; no contact_status / close-window filters; rows without `contact_email` can’t drill down |
| **Contact panel** | `GET /contacts/{email}`; suppression banner; outreach truth guide; identity/outreach/sent | No link back to warm/equipment row; no “in current queue” hint; minimal profile empty state is easy to miss |
| **Empty / reduced** | Per-table empty vs filter-empty; `reduced_mode` + `meta.note` | No global “data may be stale” from operator status age; limited vs filtered not explained when `limit` truncates |

**Hard constraints (unchanged):** no bodies, no `source_path`/`sqlite_path` in UI, no send/draft/archive/mark-contacted, Postgres mirror ≠ send truth.

---

## Ranked improvements

Priority = operator usefulness × feasibility ÷ risk. **P0** = first slice candidates.

| Rank | Theme | Improvement | Client-only? | API needed? |
|------|-------|-------------|--------------|-------------|
| **1** | Warm prioritization | **“Needs attention” preset**: sort/filter boosting `problem`, `client_reply`, `waiting_client`, `quote_sent`; optional hide `bounce` when not in “show noise” mode | Yes (sort key + filter chips on loaded rows) | Optional later: `sort=operator` or `priority_rank` on `WarmCaseItem` |
| **2** | Equipment triage | **Triage toolbar**: filter by `contact_status`, `safe_channel`, `next_action`; preset “closing soon” (close_date within N days); default sort rank asc + close_date asc | Yes on loaded set; **partial** if queue > limit | Yes for faithful triage: pass `priority`, `safe_channel`, `next_action` query params; optional `limit` bump (read-only load) |
| **3** | Empty / stale states | **Truncation footnote**: “Loaded 30 of {meta.count} — narrow filters or increase limit (API)” when `count > items.length` | Yes | Optional: `meta.truncated`, `meta.fetched_at`, sync watermark in `/operator/status` |
| **4** | Operator warnings | **Expand all warnings** (remove `WARNINGS_PREVIEW=5` cap or collapsible full list); optional group by keyword (DNR, manifest, staleness) | Yes | Optional: structured `warnings[]` with `{code, severity, contact_email?}` |
| **5** | Contact clarity | **Queue context in panel**: “In warm cases” / “In equipment queue” badges from **loaded** table rows; jump highlight row on close | Yes (join on `contact_email` in memory) | Optional: `in_warm_queue`, `in_equipment_queue` on `ContactDetailResponse` |
| **6** | Warm prioritization | **Relative timestamps** (“hace 2 días”) for `last_seen_at` / equipment `close_date` | Yes | — |
| **7** | Contact clarity | **Stronger minimal profile**: explain 404 vs empty intelligence vs mirror-only; mirror banner always when `backend=postgres` | Yes | Optional: richer `meta.note` codes |
| **8** | Warm prioritization | **Expose `days` + `include_noise`** as read-only query toggles (reload fetch) | No (new query params on fetch) | Already supported on `GET /cases/warm` |
| **9** | Equipment triage | **Highlight missing contact email** (badge on row; triage filter “has email”) | Yes | Optional: API flag `contact_email_present` |
| **10** | Warm prioritization | **Safe Gmail deep link** when API `gmail_url` is allowlisted `https://mail.google.com/...` | Yes (parser + link policy test) | Already on `WarmCaseItem`; today intentionally nulled in `commercialParse.ts` |
| **11** | Operator warnings | **Warning → table link**: if warning mentions licitación/buyer token present in equipment haystack, scroll/highlight (heuristic) | Yes | Fragile; low priority |
| **12** | Empty / stale | **Global stale banner** when operator status warnings mention staleness / manifest age | Yes (parse existing strings) | Better: `manifest_age_hours` in `/operator/status` |
| **13** | Contact clarity | **Related messages count / recent subject list** (no body) | No | New GET fields or sub-resource (larger scope) |
| **14** | Equipment triage | **Cross-link warm `equipment_signal` ↔ equipment category** filter | Yes (client join) | — |
| **15** | Empty / stale | **Section-level skeleton** consistency + retry all on partial failure | Yes | — |

---

## By theme (detail)

### 1. Warm cases prioritization

**Today:** Server orders by `last_seen_at DESC`; client can sort by status/category/contact. Status order in `warmCaseTableView.ts` already elevates `problem` when sorting by status.

**Proposed (client-only):**

- New sort preset **“Needs attention”**: `problem` → `client_reply` → `waiting_client` → `quote_sent` → `open` → `waiting`, then `last_seen_desc` within tier.
- Quick filters: **“Replies”** (`client_reply`, `supplier_reply`), **“Waiting”** (`waiting_client`, `waiting_supplier`), **“Problems”** (`problem`, `bounce` if noise included).
- Chip **“Has equipment signal”** when `equipment_signal` non-empty.
- Default **hide internal contacts** to *on* for warm only? (product choice — today default off to avoid hiding data silently).

**API (later):**

- Query `sort=operator_priority` implemented in `build_warm_cases_response` / SQLite queue (single source of truth for ordering).
- Document interaction with `positive_signal_only` (API default `true`, dashboard client uses `false`).

### 2. Equipment opportunities triage

**Today:** Manifest rank + CSV fields; client sort only on loaded 30 rows.

**Proposed (client-only):**

- Filters: `contact_status`, `safe_channel`, `next_action` (dropdowns from unique values in loaded set).
- Presets: **“Closing ≤14d”**, **“Has contact email”**, **“Needs supplier”** (`supplier_needed` / `needs_supplier_quote`).
- Secondary sort: rank asc, then close_date asc (composite sort key).

**Proposed (API wiring — still GET):**

- Pass through existing query params in `fetchEquipmentOpportunities`: `priority`, `safe_channel`, `next_action`, `include_account_intelligence=false` for leaner operator view.
- Consider `limit=50` for Today only (load test; keep ≤200 cap).

### 3. Operator warnings

**Today:** `TodayPage` slices `warnings.slice(0, 5)`; email substrings open contact panel (2.5).

**Proposed:**

- Show all warnings in collapsible section; keep email drilldown.
- Optional: icon/label by heuristic (`do not repeat`, `stale`, `manifest`, `postgres`) — still read-only text.
- Do **not** add mailto from warnings (policy).

### 4. Contact profile clarity

**Proposed:**

- Header badges: **Warm queue** / **Equipment queue** if email appears in currently loaded tables (client join).
- On open from warm row: show **subject + category + status** snippet at top (from row, no extra fetch).
- Clarify **404** vs **200 minimal profile** vs **suppression** in copy.
- TokenLabel for outreach `state` / `source` (reuse 2.5 labels).

### 5. Empty / reduced / stale states

**Proposed:**

- When `meta.reduced_mode`: actionable copy pointing to RUNBOOK/sync (link in doc only, not filesystem paths in UI).
- When `loaded < meta.count`: truncation warning (warm + equipment).
- When panel + tables all empty after successful load: **“Queues empty — check pipeline ingest and active/current manifest”** (no script buttons).
- Partial error UX: one section failed → retry that section without clearing others (already per-table retry; add short “other sections loaded” note).

---

## Client-only vs API support

| Work package | Client-only | Needs `apps/api` |
|--------------|-------------|------------------|
| Warm “needs attention” sort + reply/waiting chips | ✓ | — |
| Relative dates | ✓ | — |
| Equipment dropdown filters on loaded rows | ✓ | — |
| Equipment triage presets calling query params | — | ✓ (wire existing params) |
| Truncation footnote | ✓ (from `meta.count`) | Optional `truncated: true` |
| Expand warnings | ✓ | — |
| Contact queue badges | ✓ (loaded rows) | Optional flags on contact detail |
| Gmail link (allowlisted URL) | ✓ | Field already exists |
| `days` / `include_noise` toggles | ✓ (refetch) | Params exist |
| Operator priority sort at source | — | ✓ new sort semantics |
| Structured warnings | — | ✓ schema change |

---

## Risks

| Risk | Mitigation |
|------|------------|
| **False priority** — client heuristics disagree with pipeline | Label presets “display order only”; don’t imply send approval; prefer API sort in slice 2 |
| **Truncation blind spot** — only 30 rows loaded | Truncation footnote + optional higher `limit`; avoid implying full queue scanned |
| **Postgres mirror staleness** | Keep mirror banner; don’t show `READY` as outreach green light; optional stale age in status |
| **Gmail URL** | Allowlist host/path; never render if not `https://mail.google.com/`; keep policy tests |
| **Warning heuristics** | Grouping by substring only; don’t parse as executable instructions |
| **Scope creep** | No pagination UI, no write, no `/mirror/*` on Today, no new tables in API |

---

## Recommended first implementation slice (Dashboard-2.6a)

**Goal:** Maximum operator value with **zero API schema changes** and minimal diff.

1. **Warm:** add sort preset “Needs attention” + quick filter chips (replies / waiting / has equipment signal).
2. **Equipment:** add client filters (`contact_status`, `safe_channel`, `next_action`, has email, closing soon) + composite sort (rank + close date).
3. **States:** truncation footnote when `meta.count > items.length`; improve reduced-mode copy (no paths).
4. **Warnings:** remove 5-item cap (collapsible “All warnings”).
5. **Contact panel:** queue badges + warm-row context header when opened from table.
6. **Polish:** relative timestamps in both tables.

**Tests (when implementing):** extend `warmCaseTableView.test.ts`, `equipmentTableView.test.ts`, `TodayPage.test.tsx`, `ContactProfilePanel.test.tsx`; no new API tests unless query wiring added.

**Dashboard-2.6b (follow-up):** wire equipment API query params + optional `limit=50`; allowlisted `gmail_url` link; `days`/`include_noise` warm toggles.

**Dashboard-2.6c (API):** operator priority sort for warm cases; structured warnings — only if 2.6a proves insufficient.

---

## Out of scope (Dashboard-3+)

- Write/send/archive/mark-contacted
- `/mirror/*` routes on Today
- Pagination / infinite scroll across full DB
- Raw bodies, attachment previews
- Supabase implementation
- Replacing SQLite/CSV operational truth

---

## References

- [V1_FREEZE_OPERATOR_HANDOFF.md](./V1_FREEZE_OPERATOR_HANDOFF.md)
- [apps/api/README.md](../../api/README.md) — route contracts
- [docs/PROJECT_CONTEXT.md](../../../docs/PROJECT_CONTEXT.md) — architecture entrypoint
- Code: `TodayPage.tsx`, `WarmCasesTable.tsx`, `EquipmentOpportunitiesTable.tsx`, `ContactProfilePanel.tsx`, `warmCaseTableView.ts`, `equipmentTableView.ts`, `commercialParse.ts`
