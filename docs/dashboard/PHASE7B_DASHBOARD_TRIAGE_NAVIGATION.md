# Phase 7B — Dashboard triage navigation (design)

**Status:** Design only (Phase 7A delivers classification + tests; no major UI routing yet).

**Goal:** Separate operator views so warm mail is not one undifferentiated “client” queue.

---

## Proposed top-level navigation

| Section | Purpose | Primary data sources |
|---------|---------|-------------------|
| **Today** | Operator verdict, summary KPIs, shortcuts | `/health`, `/operator/status` |
| **Inbox triage** | All warm threads with role filter chips | `GET /cases/warm` (role categories) |
| **Opportunities** | Equipment / tender signals | `GET /opportunities/equipment` |
| **Deals** | Redacted commercial deal mirror | `GET /mirror/commercial/deals` |
| **Suppliers** | Supplier quotes + follow-ups | Warm cases: `supplier_quote_received`, `supplier_followup` |
| **Tenders** | Public procurement queue (future) | Equipment mirror + tender metadata |
| **Payments & logistics** | Bank, Wise, DHL, import accounts | `payment_admin`, `logistics_admin` |
| **Contacts** | Read-only contact profile drilldown | `GET /contacts/{email}` |

---

## Role category → default section

| Role | Default section | Hidden from “Clientes reales” |
|------|-----------------|-------------------------------|
| `client_opportunity` | Opportunities / Inbox | No |
| `client_response` | Inbox triage | No |
| `deal_evidence_candidate` | Deals | No (linked in 7B+) |
| `supplier_quote_received` | Suppliers | Yes |
| `supplier_followup` | Suppliers | Yes |
| `payment_admin` | Payments & logistics | Yes |
| `logistics_admin` | Payments & logistics | Yes |
| `internal_admin` | Inbox (admin filter) or hidden | Yes |
| `system_noise` | Hidden by default | Yes |
| `bounce_problem` | Hidden / problem bucket | Yes |

---

## Phase 7B implementation notes (not in 7A)

1. Replace single **Today** table with section routes (React Router or tab state).
2. Persist last-selected triage filter per operator (localStorage).
3. **Deals** panel: link `deal_evidence_candidate` rows to `GET /mirror/commercial/deals/{deal_key}` when match exists (read-only).
4. Do not add Gmail compose, send, or SQLite write actions in any section.
5. Keep Postgres mirror labels: “Read-only · Postgres mirror” on Deals only.

---

## Safety (unchanged)

- GET-only API; no raw bodies in responses.
- No purchase-events mirror for deal UI.
- Classification changes are response-time + promotion metadata only until Alembic expands `commercial.warm_case` CHECK (future).

---

## Related

- Phase 7A classifier: `warm_case_role_classification.py`
- Current presets: `apps/dashboard/src/lib/warmCaseViewPreset.ts`
- Audit: `docs/commercial/PHASE7A_WARM_CASE_CLASSIFICATION_AUDIT.md` (if present)
