# API JSON response contract

**Audience:** Dashboard, operator tooling, and any HTTP client of `apps/api` (port **8001**).

**Scope:** Read-only operator API (`origenlab_api`). This document defines the **target contract** clients should rely on, documents **stable shapes already shipped**, and lists **known gaps** where behavior still follows FastAPI defaults.

**Non-goals (this doc):** Route refactors, error-handler rewrites, or breaking response renames. Those require a dedicated migration PR with client + test updates.

---

## Principles

| Principle | Rule |
|-----------|------|
| Predictable | Success and error bodies use documented top-level keys. |
| Consistent | List endpoints share `meta` + `items`; errors share one machine-readable envelope (target). |
| Machine-readable | Stable string `code` values for errors; typed OpenAPI `response_model` on public routes. |
| Human-debuggable | Short `message` for operators; optional safe `details` for UI hints. |
| Safe | No stack traces, secrets, raw env vars, DSNs, Gmail tokens, or full email bodies. |
| Stable | Prefer **additive** changes. Renames/removals require tests + this doc in the same PR. |

---

## Success responses

### General rules

1. Every **successful** response MUST be a **JSON object** (never a bare array or string).
2. Public routes SHOULD declare a Pydantic `response_model` (see OpenAPI `/openapi.json` in dev).
3. Do **not** expose: stack traces, `postgres://…` URLs, raw `ORIGENLAB_*` secrets, Gmail OAuth tokens, full MIME bodies, or unredacted filesystem paths in operator-facing fields.

### List endpoints (`meta` + `items`)

Collection routes return:

```json
{
  "meta": {
    "count": 0,
    "data_source": "sqlite",
    "read_only": true,
    "note": ""
  },
  "items": []
}
```

| `meta` field | Required | Notes |
|--------------|----------|-------|
| `count` | **Yes** (target) | Number of items returned (may be `0`). |
| `data_source` | Optional | e.g. `sqlite`, `postgres_mirror`, `active_current_csv`. |
| `read_only` | Optional | Should be `true` for operator read routes. |
| `note` | Optional | Human context when `reduced_mode` or empty data. |

Routes may add **documented** meta fields (e.g. `reduced_mode`, `campaign_mode`, `enrichment_available`). Clients should ignore unknown meta keys.

**Examples (shipped):**

| Route | Response model |
|-------|----------------|
| `GET /cases/warm` | `WarmCasesResponse` — `meta` + `items` |
| `GET /opportunities/equipment` | `EquipmentOpportunitiesResponse` — `meta` + `items` |
| `GET /emails/recent` | `EmailsRecentResponse` — `meta` + `items` (+ extra top-level counters documented in schema) |
| `GET /mirror/*` list routes | Pipeline mirror schemas — `meta` + `items` (or paginated variants) |

### Single-resource endpoints (`meta` + resource key)

Prefer:

```json
{
  "meta": { "read_only": true, "data_source": "sqlite" },
  "item": { }
}
```

**Stable exceptions (do not rename without migration):**

| Route | Shape | Resource key |
|-------|-------|--------------|
| `GET /contacts/{email}` | `ContactDetailResponse` | `contact` (not `item`) |
| `GET /mirror/catalog/products/{product_key}` | `CatalogProductDetailResponse` | product nested per schema |
| `GET /mirror/commercial/deals/{deal_key}` | `CommercialDealDetailResponse` | `deal` |

New single-resource routes SHOULD use `meta` + `item` unless mirroring an existing nested name.

### Health and status endpoints

Small **stable objects** are allowed when documented and covered by tests.

| Route | Shape | Notes |
|-------|-------|-------|
| `GET /health` | `{ ok, service, mode, backend, postgres_configured }` | Liveness; no `meta` wrapper. |
| `GET /operator/status` | `OperatorStatusResponse` | Flat operator verdict + warnings. |
| `GET /operator/automation-status` | `OperatorAutomationStatusResponse` | Automation health snapshot. |
| `GET /mirror/health/dependencies` | `HealthDependenciesResponse` | Postgres/SQLite reachability (redacted URL fields only). |

Keys on these endpoints must not change casually; update `tests/test_health.py` and this table together.

---

## Error responses

### Target contract (all routes)

Errors SHOULD converge on:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Short human-readable summary",
    "details": {},
    "request_id": null
  }
}
```

| Field | Type | Purpose |
|-------|------|---------|
| `code` | string | Stable machine code for client branching. |
| `message` | string | Operator-facing summary (no secrets). |
| `details` | object | Safe structured context (field names, allowed values). |
| `request_id` | string \| null | Correlation id when middleware provides one. |

### Standard `code` values

| `code` | HTTP | When |
|--------|------|------|
| `invalid_query_param` | 422 | Unknown enum/filter (e.g. invalid warm `category`). |
| `validation_error` | 422 | FastAPI/Pydantic query or path validation. |
| `not_found` | 404 | Resource missing. |
| `forbidden` | 403 | Host allowlist or policy rejection. |
| `backend_unavailable` | 503 | Postgres mirror not configured or DB unreachable. |
| `mirror_not_configured` | 503 | Mirror route without `ORIGENLAB_POSTGRES_URL`. |
| `internal_error` | 500 | Unexpected failure (no traceback in body). |

### Safety rules for errors

Never include in `message` or `details`:

- Stack traces or `traceback` text
- Raw `postgres://` / `postgresql://` connection strings
- Env var **names with values** (e.g. full `ORIGENLAB_POSTGRES_URL=…`)
- Passwords, API tickets, Gmail refresh tokens
- Full email bodies or private Gmail thread content
- Raw SQL queries

Redacted placeholders (`<redacted>`, `<unset>`) are OK when explicitly documented.

---

## OpenAPI and stability

- **Dev:** `/openapi.json`, `/docs`, `/redoc` when docs are enabled (disabled in production by default).
- Every public route MUST have a `response_model` OR a documented exception in this file.
- If a response shape changes, update **tests** (`tests/test_api_response_contract.py` + route-specific tests) and this doc in the **same PR**.
- Prefer **additive** fields. Deprecate before removing.

---

## Route inventory (GET, public)

Operator plane (SQLite / active CSV):

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/operator/status` |
| GET | `/operator/automation-status` |
| GET | `/emails/recent` |
| GET | `/cases/warm` |
| GET | `/opportunities/equipment` |
| GET | `/contacts/{email}` |

Postgres mirror (`/mirror/*`, read-only reporting):

| Method | Path |
|--------|------|
| GET | `/mirror/health/dependencies` |
| GET | `/mirror/meta/dashboard-sync` |
| GET | `/mirror/audits/gmail-interactions` |
| GET | `/mirror/dashboard/summary` |
| GET | `/mirror/classification/summary` |
| GET | `/mirror/classification/recent` |
| GET | `/mirror/classification/actions` |
| GET | `/mirror/commercial/purchase-events` |
| GET | `/mirror/commercial/purchase-events/{event_id}` |
| GET | `/mirror/commercial/deals` |
| GET | `/mirror/commercial/deals/{deal_key}` |
| GET | `/mirror/catalog/products` |
| GET | `/mirror/catalog/products/{product_key}` |
| GET | `/mirror/leads/prospects` |
| GET | `/mirror/leads/prospects/{prospect_key}` |
| GET | `/mirror/leads/summary` |
| GET | `/mirror/contacts` |
| GET | `/mirror/organizations` |
| GET | `/mirror/outbound/suppressions/emails` |
| GET | `/mirror/outbound/contact-state` |
| GET | `/mirror/outbound/readiness` |

---

## Current gaps

These are **known** deviations from the target contract. Clients must tolerate them until a migration PR lands.

### 1. Error envelope uses FastAPI `detail` (not `error`)

Today, `HTTPException` and Starlette validation errors return:

```json
{ "detail": "…" }
```

or for query validation:

```json
{ "detail": [ { "type": "…", "loc": […], "msg": "…" } ] }
```

**Examples:**

- `GET /cases/warm?category=not_a_real_category` → **422**, `detail` string listing allowed categories.
- `GET /cases/warm?limit=0` → **422**, `detail` array (Pydantic `ge=1` violation).
- `GET /contacts/not-an-email` → **422**, `detail` string from `ValueError`.
- `GET /mirror/...` 404 → **404**, `detail` short string (e.g. `"catalog product not found"`).
- Unknown path → **404**, `detail`: `"Not Found"`.
- Host allowlist reject → **403**, `detail`: `"Forbidden"`.

**TODO:** Global exception handlers to normalize into `error.code` / `error.message` / `error.details` without breaking dashboard parsers in one step.

### 2. No `request_id` on errors yet

Correlation ids are not attached to JSON error bodies.

### 3. Legacy resource key names

- `GET /contacts/{email}` uses `contact`, not `item` — **stable; do not rename casually**.

### 4. Health / operator status omit `meta`

Flat objects are intentional for liveness and operator verdict routes (see table above).

### 5. `EmailsRecentResponse` extra top-level fields

Besides `meta` + `items`, includes `total_returned`, `days_window`, `scope_note`, etc. Documented in `schemas/emails.py`; clients should treat unknown keys as optional.

---

## Client checklist

- [ ] Parse success bodies as objects; never assume a top-level array.
- [ ] For lists, read `meta.count` and `items`.
- [ ] Branch on HTTP status first; then `error.code` (future) or `detail` (today).
- [ ] Treat unknown JSON keys as optional (forward-compatible).
- [ ] Do not log full error bodies in production if they might contain user input; our API should not echo secrets.

---

## Tests

Contract smoke tests live in:

```bash
cd apps/api
uv run pytest tests/test_api_response_contract.py -q
```

Full suite:

```bash
uv run pytest -q
```
