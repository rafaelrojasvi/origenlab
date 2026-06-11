# Operator dashboard — information architecture

Status: canonical (product / IA planning)  
Owner: dashboard-maintainers  
Last reviewed: 2026-06-11

Related: [`V1_FREEZE_OPERATOR_HANDOFF.md`](./V1_FREEZE_OPERATOR_HANDOFF.md) · [`../../api/README.md`](../../api/README.md) · [`../../email-pipeline/docs/pipeline/SCHEMA_CLASSIFICATION_MODEL.md`](../../email-pipeline/docs/pipeline/SCHEMA_CLASSIFICATION_MODEL.md) · [`../../docs/PROJECT_CONTEXT.md`](../../docs/PROJECT_CONTEXT.md)

---

## 1. Product framing

The OrigenLab operator dashboard is a **read-only cockpit** for commercial email intelligence. It helps a human operator answer:

- What needs attention today?
- Who is this contact / organization?
- What stage is this deal or opportunity in?
- Is it safe to consider outreach (information only — never approval from the UI)?
- Is automation and the read mirror healthy?

It is **not**:

- An email client (no compose, reply, archive, or label edits)
- A send tool (no send / schedule / campaign launch)
- A CRM write surface (no stage updates, owner assignment, or note persistence from the browser)
- Operational truth for outbound (SQLite + sidecars remain authoritative)

Language in the UI should stay **solo lectura** / human-review oriented. Mirror and Postgres labels must not imply send approval.

---

## 2. Source-of-truth boundaries

```text
Gmail / archive ingest
  → SQLite operational truth (emails, sidecars, mart tables, safety memory)
  → email_mart_features (fast derived features; rebuildable)
  → business mart + warm-case heuristics + lead research overlays
  → Postgres read mirror (mart.*, reporting.*, lead_intel.*, api views)
  → apps/api GET routes (:8001)
  → apps/dashboard React UI (:5173)
```

| Layer | Role | Dashboard may show | Dashboard must not treat as send approval |
|-------|------|-------------------|-------------------------------------------|
| **Gmail / IMAP** | Raw mailbox | Subject, snippet, safe subject lines, counts | Full bodies, mutation |
| **SQLite `emails`** | Canonical message evidence | Recent previews via API | Entire archive as “queue truth” |
| **Safety sidecars** | `contact_email_suppression`, `contact_domain_suppression`, `outreach_contact_state` | Contact panel warnings | “Green light to send” |
| **Warm cases** | Heuristic operator queue from canonical Gmail + enrichment | `/cases/warm`, Bandeja, Proveedores | Complete Gmail history |
| **Lead research** | Derived prospect queue (`lead_research_prospect` → mirror) | Prospectos, Clientes / instituciones | `classification` alone |
| **Postgres mirror** | Read-optimized reporting | Lists, KPIs, mirror routes | Outbound or safety authority |
| **active/current CSV/JSON** | Generated operator artifacts | Equipment queue, manifests | Live Gmail state |

Automation loops (read-only in UI):

- **Gmail → SQLite:** debounced `auto-refresh-mail`
- **SQLite → Postgres/dashboard:** debounced `auto-mirror-dashboard` + `daily-core`

See [`OPERATOR_CRON.md`](../../email-pipeline/docs/pipeline/OPERATOR_CRON.md) and `GET /operator/automation-status`.

---

## 3. Navigation model (current vs target)

### 3.1 Shipped today (React shell)

| Nav group | Section id | Label | Primary operator question |
|-----------|------------|-------|---------------------------|
| Inicio | `today` | Hoy | What should I look at first today? |
| Inicio | `inbox` | Bandeja de revisión | Which warm threads need triage by role? |
| Comercial | `deals` | Negocios | Where are active commercial deals and blockers? |
| Comercial | `prospectos` | Prospectos | Which researched leads need human review? |
| Comercial | `contacts` | Clientes / instituciones | Which buyer institutions and contacts matter? |
| Operación | `tenders` | Licitaciones / equipos | Which public equipment opportunities are live? |
| Operación | `payments-logistics` | Pagos y logística | What payment / logistics admin needs review? |
| Operación | `suppliers` | Proveedores | Which supplier threads need follow-up? |
| Operación | `catalogo` | Catálogo | What products can we quote? |
| Sistema | `system` | Sistema | Is the stack healthy and read-only policy clear? |

### 3.2 Target IA buckets (planning vocabulary)

These names map the **product** to helpdesk / CRM mental models. Several are already covered by shipped sections; others are **future consolidation** targets—not new write surfaces.

| Target page | Maps to (current / planned) | Notes |
|-------------|------------------------------|-------|
| **Today** | `today` | Command center KPIs + deep links |
| **Inbox Intelligence** | `inbox` + classification mirror (future) | Queue + intent/direction lens on recent mail |
| **Warm Cases** | `inbox`, `suppliers`, slices of `payments-logistics` | `/cases/warm` is the shared row model |
| **Contacts** | `contacts` + `GET /contacts/{email}` drilldown | Institution workspace + contact side panel |
| **Organizations** | Mirror `/mirror/organizations` (no dedicated page yet) | Org rollups from mart |
| **Opportunities** | `tenders` + `prospectos` + equipment CSV | Mixed public tender + research leads |
| **Automation / System** | `system` + `AutomationHealthCard` | Operator + automation status |

**Rule:** New UI should extend this IA—not add parallel routes that duplicate the same queue with different names.

---

## 4. Page specifications

### 4.1 Today (`today`)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Single-screen operational snapshot for the current shift |
| **Primary question** | “What needs my attention right now?” |
| **Main cards** | Operator verdict; summary counts (clientes por responder, proveedores, negocios, licitaciones, catálogo); automation health; daily-core note; warnings preview |
| **Tables** | None (navigation hub only) |
| **Filters** | None |
| **Empty state** | “Sin datos cargados” when warm/equipment fetches fail; link to Sistema |
| **API** | `GET /health`, `GET /operator/status`, `GET /cases/warm` (counts), `GET /opportunities/equipment`, mirror summaries optional |

### 4.2 Inbox Intelligence (`inbox` → future classification lens)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Role-filtered warm-case triage (client vs supplier vs admin noise) |
| **Primary question** | “Which conversations should I open first in this role?” |
| **Main cards** | Optional KPI chips per preset (clientes reales, proveedores, pagos, logística) |
| **Table columns** | Contacto, Cuenta, Estado, Categoría, Última actividad, Equipo/señal, Asunto (+ vista previa), Próxima acción |
| **Filters** | View presets, status, category, search, hide internal contacts, sort |
| **Empty state** | “No hay casos en esta vista” / reduced-mode note when API omits enrichment |
| **API** | `GET /cases/warm`; future: `GET /mirror/classification/recent`, `/mirror/classification/actions` |

**Future Inbox Intelligence additions (read-only):** direction (`inbound`/`outbound`), intent label, confidence chip, evidence link to `email_id` list—never raw body.

### 4.3 Warm Cases (shared row model)

Warm cases are the **canonical thread row** across Bandeja, Proveedores, and filtered slices.

| Field | Meaning |
|-------|---------|
| `case_id` | Stable row id (often normalized email) |
| `contact_email` | Primary counterparty |
| `account_name` | Display org / account |
| `category` | Heuristic commercial role (see §5) |
| `status` | Queue state (`new`, `open`, `waiting`, `quoted`, `problem`) |
| `next_action` | Suggested operator verb (display only) |
| `last_seen_at` | Last activity timestamp |
| `grouped_email_count` | Collapsed messages in thread (mirror case depth, not full Gmail) |
| `snippet` | Redacted preview only |

**Primary question:** “What is the latest safe summary of this thread, and what hat am I wearing (client/supplier/admin)?”

### 4.4 Contacts — Clientes / instituciones (`contacts`)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Buyer institution workspace from lead mirror (not supplier CRM) |
| **Primary question** | “Which institutions have mirror-matched Gmail history and who are the contacts?” |
| **Main cards** | Instituciones; Con historial Gmail en espejo; Sin email / investigar; Seguras para revisar; Bloqueadas / revisar |
| **Table columns** | Institución, Contactos, Historial Gmail (espejo vs detectado), Score, Sector/región, Estado chips, Próxima acción |
| **Filters** | Search, preset (todas, contactar, Gmail, falta email, bloqueadas), sector, región, min score |
| **Empty state** | Friendly mirror load error card; “Sin instituciones para los filtros actuales” |
| **Drawer** | Institution summary, contacts table, Gmail espejo vs detectado, prospect sources, safety note |
| **API** | `GET /mirror/leads/prospects` (limit 100), optional `GET /mirror/leads/prospects/{key}` |

**Copy rule:** Distinguish **historial en espejo** (published matches) from **Gmail detectado** (sent/received counts on prospect rows). Do not imply full mailbox coverage.

**Contact drilldown (global):** `GET /contacts/{email}` side panel from any page with email buttons—outreach state, suppression, sent history (no body).

### 4.5 Organizations (planned dedicated page)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Org-centric rollups from business mart |
| **Primary question** | “What do we know about this organization across contacts and signals?” |
| **Main cards** | Total orgs; With opportunities; With recent activity; Suppressed domains |
| **Table columns** | Organization, domain, sector, contact count, last activity, opportunity count, flags |
| **Filters** | Search, sector, has_contacts, has_opportunities |
| **Empty state** | “Espejo no sincronizado” when mart empty |
| **API (today)** | `GET /mirror/organizations` (paginated); not mounted as primary dashboard page yet |

### 4.6 Opportunities (composite)

| Sub-area | Section | Source |
|----------|---------|--------|
| Public equipment / tenders | `tenders` | `GET /opportunities/equipment` (active/current CSV or mirror) |
| Research leads | `prospectos` | `GET /mirror/leads/prospects`, `/mirror/leads/summary` |
| Commercial deals | `deals` | `GET /mirror/commercial/deals` |

**Primary question:** “Where is there a commercial opportunity worth human review?”

**Non-goal:** Editing pipeline stage from UI.

### 4.7 Proveedores (`suppliers`)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Supplier workspace over warm-case slice |
| **Primary question** | “Which supplier needs follow-up on quotes or threads?” |
| **Main cards** | Proveedores; Cotizaciones recibidas; Seguimientos; Hilos activos |
| **Layout** | Split: provider list + selected detail + warm table |
| **Provider card** | `N caso(s) en espejo · M+ mensajes Gmail detectados` when `grouped_email_count > 1` |
| **API** | `GET /cases/warm` filtered client-side to supplier categories |

### 4.8 Automation / System (`system`)

| Aspect | Definition |
|--------|------------|
| **Purpose** | Read-only health, scope education, mirror metadata |
| **Primary question** | “Is automation healthy and is the mirror snapshot visible?” |
| **Main cards** | AutomationHealthCard (verdict, snapshot summary, mail loop, mirror loop, daily-core timestamps) |
| **Snapshot copy (when state exists)** | `Snapshot local publicado · última actualización · daily-core visible · mirror visible` |
| **Snapshot copy (missing)** | `Snapshot local no publicado` + publish/review locally guidance |
| **API** | `GET /operator/automation-status`, `GET /operator/status`, `GET /mirror/meta/dashboard-sync` |

---

## 5. Classification taxonomy

Operator-facing labels are Spanish in the UI; API stores English snake_case tokens. See [`prospectLabels.ts`](../src/lib/prospectLabels.ts) and [`operatorLabels.ts`](../src/lib/operatorLabels.ts).

### 5.1 Direction (planned / partial in mart)

| Value | Meaning |
|-------|---------|
| `inbound` | Counterparty initiated or reply received |
| `outbound` | OrigenLab sent or campaign-originated |
| `internal` | OrigenLab / labdelivery domains |
| `unknown` | Insufficient signal |

### 5.2 Intent (email_mart_features / classification mirror)

High-level commercial intent (examples—exact enum in pipeline):

| Intent | Operator meaning |
|--------|------------------|
| `quote_request` | Buyer asking for pricing |
| `quote_response` | Supplier or self quote delivery |
| `follow_up` | Thread continuation without new ask |
| `payment_admin` | Transfers, invoices, banking |
| `logistics` | Shipping, import, DHL |
| `noise` | Auto-replies, bounces, system |

### 5.3 Warm case category (`category` on `/cases/warm`)

| Category | Role |
|----------|------|
| `client_opportunity`, `client_response`, `client_reply`, `opportunity` | Buyer / revenue |
| `supplier_quote_received`, `supplier_followup`, `supplier_reply`, `waiting_supplier` | Supplier |
| `payment_admin`, `payment_received` | Treasury |
| `logistics_admin`, `vendor_logistics` | Logistics |
| `internal_admin`, `system_noise`, `auto_acknowledgement`, `bounce`, `bounce_problem` | Noise / problem |
| `quote_sent`, `waiting_client`, `campaign_outreach`, `waiting_campaign_reply` | Workflow hints |
| `deal_evidence_candidate` | Deal ledger linkage candidate |

### 5.4 Queue status (`status`)

| Status | Meaning |
|--------|---------|
| `new` | Recently surfaced |
| `open` | Active review |
| `waiting` | Blocked on counterparty or time |
| `quoted` | Quote lifecycle stage hint |
| `problem` | Bounce / deliverability / anomaly |

### 5.5 Waiting on (`waiting_on` — target field)

| Value | Meaning |
|-------|---------|
| `client` | Need buyer action |
| `supplier` | Need vendor quote/info |
| `internal` | Need OrigenLab operator |
| `bank` | Payment confirmation |
| `carrier` | Logistics provider |
| `none` | No explicit wait |

*Not yet exposed on all warm rows—plan as derived display field.*

### 5.6 Commercial stage (deals mirror)

From `GET /mirror/commercial/deals`: `deal_status`, `margin_status`, `reconciliation_status`, `freight_status`—read-only deal ledger semantics.

### 5.7 Lead prospect classification (mirror / Prospectos)

Examples: `net_new_safe_review`, `same_domain_contacted_review`, `old_gmail_prospect_review`, `research_only_contact_needed`, `already_contacted_block`. **Never** auto-approve send from classification alone ([golden rule](../../email-pipeline/docs/pipeline/SCHEMA_CLASSIFICATION_MODEL.md)).

### 5.8 Evidence & confidence (target)

| Concept | Source | UI rule |
|---------|--------|---------|
| `evidence_flags` | Lead prospect rows | Chips only; no raw URLs to internal paths |
| `risk_flags` | Lead research | Amber chips + drawer |
| `confidence` | Classification / lead research | Label + short explain text |
| `email_ids` | Mart features | Internal detail panel only; no export |

---

## 6. Postgres read models

### 6.1 Must-have in mirror (now)

| Model / view area | Purpose |
|-------------------|---------|
| `mart.contact_master` / `_canonical` | Contact rollups for mirror lists |
| `mart.organization_master` / `_canonical` | Organization rollups |
| `mart.opportunity_signals` / `_canonical` | Opportunity-ish signals (where populated) |
| `api.v_warm_cases` (or equivalent) | Warm case queue for postgres backend |
| `reporting.dashboard_sync_run` | Sync watermark / metadata |
| `reporting.email_classification_canonical` | Classification KPIs |
| `lead_intel.*` | Prospect research mirror |
| `commercial.*` | Deals, purchase events |
| Automation status snapshot | Published via API reading local state files or future mirror table |

### 6.2 Maybe later

| Model | Why later |
|-------|-----------|
| `recent_email_classifications` | Dedicated inbox intelligence feed |
| `classification_evidence` | Per-email explainability drilldown |
| `case_timeline` | Ordered events per case_id |

### 6.3 Explicitly not in mirror (now)

- Full email bodies (`body`, HTML)
- Raw Gmail API payloads
- Send approval internals / export gate raw rows
- Secrets, OAuth tokens, IMAP credentials
- Filesystem paths (`sqlite_path`, `active_current` paths) in JSON consumed by UI

---

## 7. API endpoint plan

### 7.1 Operator plane (SQLite or postgres-backed lists)

| Method | Path | Status | Consumer |
|--------|------|--------|----------|
| GET | `/health` | Shipped | Shell backend chip |
| GET | `/operator/status` | Shipped | Today, Sistema |
| GET | `/operator/automation-status` | Shipped | AutomationHealthCard |
| GET | `/emails/recent` | Shipped | Future inbox intelligence |
| GET | `/cases/warm` | Shipped | Bandeja, Proveedores, Pagos |
| GET | `/opportunities/equipment` | Shipped | Licitaciones |
| GET | `/contacts/{email}` | Shipped | Contact side panel |

### 7.2 Mirror plane (`GET /mirror/*`)

| Path | Status | Consumer |
|------|--------|----------|
| `/mirror/dashboard/summary` | Shipped | Future Today KPIs |
| `/mirror/meta/dashboard-sync` | Shipped | Sistema |
| `/mirror/classification/summary` | Shipped | Future inbox KPIs |
| `/mirror/classification/recent` | Shipped | Future inbox table |
| `/mirror/classification/actions` | Shipped | Triage actions |
| `/mirror/contacts` | Shipped | Legacy parked UI only |
| `/mirror/organizations` | Shipped | Future org page |
| `/mirror/commercial/deals` | Shipped | Negocios |
| `/mirror/leads/prospects` | Shipped | Prospectos, Clientes |
| `/mirror/catalog/products` | Shipped | Catálogo |
| `/mirror/outbound/*` | Shipped | Read-only safety context (not send UI) |

**Dashboard rule:** Operator shell uses operator routes first; mirror routes for reporting-heavy pages. No new write routes.

### 7.3 Planned aliases (documentation only)

| Proposed name | Maps to |
|---------------|---------|
| `/classifications/summary` | `/mirror/classification/summary` |
| `/organizations` | `/mirror/organizations` or thin operator wrapper |
| `/opportunities` | Composite of equipment + lead prospects (no single table) |

---

## 8. Example JSON shapes

### 8.1 Warm case item (`GET /cases/warm`)

```json
{
  "meta": {
    "data_source": "sqlite",
    "read_only": true,
    "reduced_mode": false,
    "count": 42,
    "enrichment_available": true,
    "note": ""
  },
  "items": [
    {
      "case_id": "buyer@acme.cl",
      "last_email_id": 1284401,
      "last_seen_at": "2026-06-10T13:38:54-04:00",
      "account_name": "ACME Labs",
      "contact_email": "buyer@acme.cl",
      "subject": "Re: Cotización equipos laboratorio",
      "category": "client_opportunity",
      "status": "open",
      "next_action": "reply",
      "equipment_signal": "centrifuga",
      "snippet": "Gracias por la cotización, necesitamos plazo de entrega…",
      "gmail_url": null,
      "grouped_email_count": 3
    }
  ]
}
```

### 8.2 Contact profile (`GET /contacts/{email}`)

```json
{
  "meta": {
    "data_source": "sqlite",
    "read_only": true,
    "reduced_mode": false,
    "note": "No enviar desde el panel; revisar sidecars en SQLite."
  },
  "contact": {
    "email": "buyer@acme.cl",
    "normalized_email": "buyer@acme.cl",
    "name": "María Pérez",
    "domain": "acme.cl",
    "organization_name": "ACME Labs",
    "organization_domain": "acme.cl",
    "last_seen_at": "2026-06-10T13:38:54-04:00",
    "first_seen_at": "2024-03-01T10:00:00-03:00",
    "message_count": 12
  },
  "outreach": {
    "state": "not_contacted",
    "last_contacted_at": null,
    "source": "outreach_contact_state",
    "notes": null,
    "do_not_repeat": false,
    "suppressed_email": false,
    "suppressed_domain": false
  },
  "sent_history": {
    "sent_count": 0,
    "latest_sent_at": null,
    "latest_subject": null
  },
  "warnings": []
}
```

### 8.3 Organization list row (`GET /mirror/organizations`)

```json
{
  "items": [
    {
      "organization_key": "org:acme.cl",
      "name": "ACME Labs",
      "domain": "acme.cl",
      "sector": "Laboratorios",
      "contact_count": 4,
      "last_seen_at": "2026-06-10T13:38:54+00:00",
      "opportunity_signal_count": 1
    }
  ],
  "total": 120,
  "read_only": true,
  "data_source": "postgres_mirror"
}
```

### 8.4 Opportunity signal (composite)

**Equipment row** (`GET /opportunities/equipment`):

```json
{
  "priority_rank": 1,
  "codigo_licitacion": "1234-56-LP25",
  "buyer": "Hospital Regional",
  "region": "RM",
  "close_date": "2026-07-15",
  "equipment_category": "centrifuga",
  "item_description": "Centrífuga refrigerada…",
  "next_action": "review",
  "safe_channel": "mercado_publico_bid",
  "supplier_needed": "yes",
  "contact_status": "pending",
  "contact_email": "compras@hospital.cl",
  "operator_note": ""
}
```

**Lead prospect row** (`GET /mirror/leads/prospects`):

```json
{
  "prospect_key": "uchile-lab",
  "organization_name": "Universidad de Chile",
  "email": "lab@uchile.cl",
  "domain": "uchile.cl",
  "final_score": 82,
  "classification": "old_gmail_prospect_review",
  "gmail_sent_count": 5,
  "gmail_received_count": 2,
  "gmail_last_contacted_at": "2025-11-01",
  "is_blocked": false,
  "recommended_next_action": "Revisar historial"
}
```

### 8.5 Automation status (`GET /operator/automation-status`)

```json
{
  "generated_at_utc": "2026-06-11T12:00:00+00:00",
  "verdict": "healthy",
  "recommended_action": "none",
  "daily_core": {
    "exists": true,
    "status": "success",
    "generated_at_utc": "2026-06-11T11:48:00+00:00",
    "age_seconds": 720
  },
  "mail_auto_refresh": {
    "state_exists": true,
    "dirty": false,
    "last_successful_refresh_at": "2026-06-11T11:50:00+00:00",
    "last_seen_inbox_total": 403,
    "last_seen_sent_total": 1018
  },
  "dashboard_auto_mirror": {
    "state_exists": true,
    "last_successful_mirror_at": "2026-06-11T11:55:00+00:00",
    "mirror_matches_daily_core": true
  },
  "warnings": []
}
```

---

## 9. Design inspirations (read-only mapping)

| Pattern | Borrow | OrigenLab adaptation |
|---------|--------|----------------------|
| **Helpdesk queue** | Status, priority, last activity, waiting_on | Warm `status`, `category`, `next_action`, `last_seen_at` |
| **Shared inbox** | Team queue, assignment | No assignment writes; presets by role (cliente/proveedor) |
| **CRM account** | Organization → contacts → deals | Clientes / instituciones + Negocios mirror |
| **CRM opportunity** | Stage, next step | Equipment + prospect rows; no stage edit |
| **Email intelligence** | Classification + confidence + evidence | Mart + lead flags; snippets only |
| **SRE dashboard** | Service health, last sync | Automation card + dashboard-sync metadata |

---

## 10. Non-goals (hard)

| Non-goal | Rationale |
|----------|-----------|
| Send button / compose / reply | Outbound stays CLI + human gates |
| Gmail label/archive/star from UI | No mailbox mutation |
| Postgres write UI | Mirror is read-only |
| SQLite mutation from browser | Safety truth stays server-side |
| CSV export of contacts for bulk send | Export gates are pipeline scripts |
| Showing raw email bodies | Policy + security |
| Treating mirror `READY` as send approval | Golden rule in SCHEMA_CLASSIFICATION_MODEL |
| Autonomous AI actions | Tatiana copilot stays outside dashboard write path |

---

## 11. Next UI work checklist (use this doc before coding)

Before adding a page, card, or column:

1. Which **primary operator question** does it answer?
2. Which **API route** already exists? If none, is it mirror or operator plane?
3. Does data come from **SQLite truth** or **postgres mirror**? Label accordingly.
4. Does the UI imply **depth** (caso en espejo vs mensajes Gmail detectados vs historial en espejo)?
5. Are **empty and error states** defined for missing mirror / reduced mode?
6. Do tests lock **column set** and **read-only** policy (no send/export)?

---

## 12. Document maintenance

Update this file when:

- Adding a new `DashboardSection` in [`dashboardNav.ts`](../src/lib/dashboardNav.ts)
- Adding a new `GET` route consumed by the dashboard
- Changing warm-case categories or prospect classifications exposed to operators
- Publishing new mart tables to Postgres mirror

Do **not** duplicate run procedures here—link to [`V1_FREEZE_OPERATOR_HANDOFF.md`](./V1_FREEZE_OPERATOR_HANDOFF.md) and email-pipeline runbooks for commands.
