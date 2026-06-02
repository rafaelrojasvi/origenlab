# Current safety checkpoint

Status: canonical (pause marker)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-01

**Stop here for this thread.** Safety/control-plane documentation and read-only audits are in place. Do not restart feature work in the wrong layer.

Related: [`POST_SEND_SAFE_LOOP.md`](POST_SEND_SAFE_LOOP.md) · [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md) · [`INSTITUTION_ALIAS_POLICY.md`](INSTITUTION_ALIAS_POLICY.md) · [`INSTITUTION_EXPLORER_SPEC.md`](INSTITUTION_EXPLORER_SPEC.md) · [`RUNBOOK.md`](../RUNBOOK.md) · [`OUTBOUND_OPERATOR_CHECKLIST.md`](OUTBOUND_OPERATOR_CHECKLIST.md)

---

## A. Current state

| Area | Status |
| --- | --- |
| **Safety / control plane** | Complete enough to **pause**. Post-send digest, NDR parser, exact bounce suppressions (operator-approved), schema layer model, Prospectos drift audit, institution grouping audit, alias policy, explorer spec — all documented or scripted. |
| **Known P0** | **None active** in this checkpoint window. |
| **Send safety** | **`contact_email_suppression`**, **`contact_domain_suppression`**, **`outreach_contact_state`**, export gates, Sent preflight — **not** `lead_research_prospect.classification`. |
| **Institution grouping** | **Read-only / display-only.** Domain-primary cards OK for exploration. No production `institution_alias` table. |
| **Presentation layer** | Dashboard labels, proposed alias seeds, explorer spec = **presentation only** — rebuildable read models. |

### Layer model (canonical)

| Layer | Truth |
| --- | --- |
| **Evidence** | `emails` (Gmail ingest) |
| **Safety** | `contact_email_suppression`, `contact_domain_suppression` |
| **Contacted lifecycle** | `outreach_contact_state` |
| **Derived queue** | `lead_research_prospect` (+ batch overlays) |
| **Presentation** | Dashboard mirror, institution aliases (future), explorer (future) |

---

## B. Golden rules

1. **Never send-gate from `lead_research_prospect.classification` alone.**
2. **Exact-email suppression wins** for that address (over domain rules for that email).
3. **Domain suppression** blocks cold outreach for the whole registrable domain.
4. **`outreach_contact_state`** = already contacted / snoozed — do not treat as “safe to cold-send.”
5. **Institution aliases / explorer never affect send gates** — display and grouping only.

Full detail: [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md) §3.

---

## C. Before any future outreach — safe loop

Run only when there is **new Sent mail, NDR/bounces, or suppression changes**:

1. **Ingest Gmail** (if needed) — read-only IMAP Sent (+ INBOX for NDR).
2. **Detect NDR / bounces** — dry-run first.
3. **Apply exact suppressions** — operator review; `--apply` is break-glass only.
4. **Refresh contacted / safety memory** — exclusion CSVs + anti-repeat exports.
5. **Rebuild post-send digest** — after contacted audit so bounce counts match SQLite.
6. **Refresh mirror** — dashboard Postgres read model.
7. **Verify JSONs** — mirror verify artifacts report `ok`.
8. **Prospectos drift audit** — report-only; drift ≠ send failure.
9. **Operator status** — expect **READY** / **mirror_ok** before trusting dashboard.

**Canonical procedure:** [`POST_SEND_SAFE_LOOP.md`](POST_SEND_SAFE_LOOP.md) (step-by-step commands).

---

## D. Commands checklist

From `apps/email-pipeline/` unless noted. Paths relative to that app.

| Step | Script | Notes |
| --- | --- | --- |
| Operator doctor | `uv run python scripts/qa/operator_status.py` | Read-only verdict first |
| Gmail ingest | `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Read-only IMAP; Sent folder per RUNBOOK |
| NDR flag / apply | `uv run python scripts/tools/flag_ndr_bounces_from_contacto.py` | Dry-run default; targeted `--emails-file` + `--only-code` + `--apply`; broad `--apply` is break-glass — see [`POST_SEND_SAFE_LOOP.md`](POST_SEND_SAFE_LOOP.md) |
| Contacted universe | `uv run python scripts/leads/audit_contacted_universe.py` | Refreshes exclusion CSVs |
| Safety memory | `uv run python scripts/qa/refresh_outbound_safety_memory.py` | DNR / contacted exports + checks |
| Post-send digest | `uv run python scripts/qa/build_post_send_digest.py` | **After** contacted audit |
| Mirror refresh | `bash scripts/ops/refresh_render_dashboard_once.sh` | Keep `RUN_OUTBOUND_SIDECAR_MIRROR=1` after campaigns |
| Prospectos drift | `uv run python scripts/qa/audit_prospectos_safety_drift.py` | Report-only; optional `--strict` |
| Institution grouping | `uv run python scripts/qa/audit_institution_grouping.py` | **Strategy / read-model only** — not send safety |
| Readiness | `uv run python scripts/qa/check_outbound_readiness.py` | Optional pre-export check |

**Verify artifacts (expect `ok`):**

- `/tmp/outbound_sidecar_mirror_verify.json`
- `/tmp/lead_research_mirror_verify.json`
- `/tmp/render_dashboard_mirror_verify.json`

**Makefile shortcuts:** `make doctor`, `make safety-refresh`, `make audit` — see [`Makefile`](../../Makefile).

---

## E. What not to do next

- Do **not** start schema migration or compact-model DDL without explicit approval.
- Do **not** simplify or merge suppression / outreach sidecar tables.
- Do **not** create **`institution_alias`** production table or auto-merge contacts.
- Do **not** build Institution Explorer as a **send surface** (no compose, export approve, suppression edit).
- Do **not** merge legacy 2016–2019 contacts into net-new without operator sign-off.
- Do **not** treat **`reports/out/`** CSVs/JSON as operational source of truth — always label generator + run time; SQLite sidecars win for safety.

---

## F. Next possible tasks (ordered)

| Priority | Task | Layer |
| --- | --- | --- |
| 1 | Run **safe loop** (§C) only when outreach or bounces change | Ops |
| 2 | Optional: Institution Explorer **API contract** detail (GET-only) — spec exists, no UI | Presentation |
| 3 | Optional: **Manual alias seed sign-off** from review pack (~34 approve candidates) | Presentation |
| 4 | Later (P1): Split prospect **`classification`** into `workflow_bucket` + safety overlay | Derived queue |
| 5 | Later: Institution Explorer **implementation** — GET-only mirror routes | Presentation |

**Do not** pick up institution/explorer/alias **implementation** until operator explicitly reopens that track.

---

## Completed in this thread (reference)

- Post-send digest tooling · NDR parser improvements · exact bounce suppressions (approved applies)
- [`SCHEMA_CLASSIFICATION_MODEL.md`](SCHEMA_CLASSIFICATION_MODEL.md)
- [`audit_prospectos_safety_drift.py`](../../scripts/qa/audit_prospectos_safety_drift.py) + post-send step
- [`audit_institution_grouping.py`](../../scripts/qa/audit_institution_grouping.py) + noise filtering
- [`INSTITUTION_ALIAS_POLICY.md`](INSTITUTION_ALIAS_POLICY.md)
- [`INSTITUTION_EXPLORER_SPEC.md`](INSTITUTION_EXPLORER_SPEC.md)

Gitignored review packs (not committed): `reports/out/active/current/institution_*`, `schema_audit_*`, `prospectos_safety_drift_*`.
