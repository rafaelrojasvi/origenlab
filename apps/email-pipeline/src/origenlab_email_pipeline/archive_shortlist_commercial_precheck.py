"""Read-only join: archive marketing shortlist × export gate × commercial intel candidates.

Used before draft generation so rows Engine-B marks ``suppressed`` / ``rejected`` are not
auto-treated as sendable just because Engine-A (export gate) passed.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from origenlab_email_pipeline.candidate_export_gate import (
    ExportGateResult,
    GateContext,
    evaluate_export_eligibility,
)

COMMERCIAL_DROP_STATUSES: frozenset[str] = frozenset({"suppressed", "rejected"})
COMMERCIAL_REVIEW_STATUSES: frozenset[str] = frozenset({"needs_review", "new", "snoozed"})


def domain_from_contact_email(contact_email: str) -> str:
    e = (contact_email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.rsplit("@", 1)[-1]


def pick_contact_email(row: Mapping[str, Any]) -> str:
    for k in ("contact_email", "email", "recipient_email"):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip().lower()
        if s:
            return s
    return ""


def pick_institution_name(row: Mapping[str, Any]) -> str:
    for k in ("institution_name", "organization_name", "org_name", "institution"):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def commercial_precheck_recommendation(
    *,
    gate_eligible: bool,
    contact_candidate: Mapping[str, Any] | None,
    organization_candidate: Mapping[str, Any] | None,
    opportunity_candidate: Mapping[str, Any] | None,
) -> str:
    """Return ``keep`` | ``review`` | ``drop`` (first safe rules, no DB)."""

    if not gate_eligible:
        return "drop"

    layers: list[Mapping[str, Any] | None] = [
        contact_candidate,
        organization_candidate,
        opportunity_candidate,
    ]
    for layer in layers:
        if not layer:
            continue
        st = str(layer.get("status") or "").strip().lower()
        if st in COMMERCIAL_DROP_STATUSES:
            return "drop"

    has_intel = any(layer is not None for layer in layers)
    if not has_intel:
        return "review"

    for layer in layers:
        if not layer:
            continue
        st = str(layer.get("status") or "").strip().lower()
        if st in COMMERCIAL_REVIEW_STATUSES:
            return "review"

    return "keep"


def _normalize_reason_codes(reason: str) -> str:
    tokens = [tok.strip() for tok in str(reason or "").replace(",", "|").split("|")]
    clean = [tok for tok in tokens if tok]
    return "|".join(clean)


def _pick_trigger_reason_codes(
    layer: Mapping[str, Any] | None,
    *,
    fallback_flags: str = "",
) -> str:
    if layer:
        raw = str(layer.get("suppression_flags") or "").strip()
        if raw:
            return _normalize_reason_codes(raw)
    return _normalize_reason_codes(fallback_flags)


def _precheck_decision_trace(
    *,
    gate_eligible: bool,
    gate_reason: str,
    contact_candidate: Mapping[str, Any] | None,
    organization_candidate: Mapping[str, Any] | None,
    opportunity_candidate: Mapping[str, Any] | None,
) -> tuple[str, str, str, str]:
    layers: list[tuple[str, Mapping[str, Any] | None]] = [
        ("contact", contact_candidate),
        ("organization", organization_candidate),
        ("opportunity", opportunity_candidate),
    ]
    if not gate_eligible:
        return (
            "drop_gate_blocked",
            "gate",
            "gate",
            "ineligible",
            _normalize_reason_codes(gate_reason),
        )
    for layer_name, layer in layers:
        if not layer:
            continue
        st = str(layer.get("status") or "").strip().lower()
        if st in COMMERCIAL_DROP_STATUSES:
            return (
                "drop_commercial_status",
                "commercial",
                layer_name,
                st,
                _pick_trigger_reason_codes(layer),
            )
    has_intel = any(layer is not None for _, layer in layers)
    if not has_intel:
        return ("review_missing_commercial_intel", "commercial", "none", "missing_intel", "")
    for layer_name, layer in layers:
        if not layer:
            continue
        st = str(layer.get("status") or "").strip().lower()
        if st in COMMERCIAL_REVIEW_STATUSES:
            return (f"review_commercial_status_{st}", "commercial", layer_name, st, "")
    return ("keep_all_checks_passed", "commercial", "none", "clear", "")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _row_to_dict(cur: sqlite3.Cursor, row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def fetch_commercial_layers(
    conn: sqlite3.Connection,
    *,
    contact_email: str,
    org_domain: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Load candidate rows keyed by contact email and org domain (lowercased)."""

    contact_row: dict[str, Any] | None = None
    org_row: dict[str, Any] | None = None
    opp_row: dict[str, Any] | None

    if _table_exists(conn, "contact_candidate"):
        cur = conn.execute(
            """
            SELECT status, suppression_flags, rationale_text, confidence_score,
                   strength_score, evidence_count, updated_at
            FROM contact_candidate
            WHERE lower(trim(contact_email)) = ?
            LIMIT 1
            """,
            (contact_email,),
        )
        contact_row = _row_to_dict(cur, cur.fetchone())

    if org_domain and _table_exists(conn, "organization_candidate"):
        cur = conn.execute(
            """
            SELECT status, suppression_flags, rationale_text, confidence_score,
                   strength_score, evidence_count, updated_at, candidate_type
            FROM organization_candidate
            WHERE lower(trim(org_domain)) = ?
            LIMIT 1
            """,
            (org_domain,),
        )
        org_row = _row_to_dict(cur, cur.fetchone())

    opp_row = None
    if org_domain and _table_exists(conn, "opportunity_candidate"):
        cur = conn.execute(
            """
            SELECT status, suppression_flags, rationale_text, confidence_score,
                   strength_score, evidence_count, updated_at, opportunity_key
            FROM opportunity_candidate
            WHERE lower(trim(org_domain)) = ?
               OR lower(trim(opportunity_key)) = ?
            LIMIT 1
            """,
            (org_domain, f"org:{org_domain}".lower()),
        )
        opp_row = _row_to_dict(cur, cur.fetchone())

    return contact_row, org_row, opp_row


def fetch_v_commercial_queue_summaries(
    conn: sqlite3.Connection,
    *,
    contact_email: str,
    org_domain: str,
) -> str:
    if not _table_exists(conn, "v_commercial_candidate_queue"):
        return ""
    cur = conn.execute(
        """
        SELECT entity_kind, status, reason_summary
        FROM v_commercial_candidate_queue
        WHERE (entity_kind = 'contact' AND lower(trim(entity_key)) = ?)
           OR (entity_kind = 'organization' AND lower(trim(entity_key)) = ?)
           OR (entity_kind = 'opportunity' AND lower(trim(org_domain)) = ?)
        ORDER BY entity_kind
        """,
        (contact_email, org_domain, org_domain),
    )
    parts: list[str] = []
    for kind, status, reason in cur.fetchall():
        parts.append(f"{kind}:{status}:{(reason or '').strip()}")
    return " | ".join(parts)


@dataclass(frozen=True)
class PrecheckSummary:
    keep: int
    review: int
    drop: int
    rows: int


def _layer_status(layer: dict[str, Any] | None) -> str:
    if not layer:
        return ""
    return str(layer.get("status") or "")


def _layer_flags(layer: dict[str, Any] | None) -> str:
    if not layer:
        return ""
    return str(layer.get("suppression_flags") or "")


def run_precheck_csv(
    *,
    conn: sqlite3.Connection,
    input_path: Path,
    out_path: Path,
    gate_ctx: GateContext,
) -> PrecheckSummary:
    """Read shortlist CSV, write review CSV; does not modify SQLite."""

    input_path = Path(input_path)
    out_path = Path(out_path)
    with input_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows_in = list(reader)

    out_rows: list[dict[str, str]] = []
    n_keep = n_review = n_drop = 0

    for raw in rows_in:
        email = pick_contact_email(raw)
        institution = pick_institution_name(raw)
        domain = domain_from_contact_email(email)
        cont: dict[str, Any] | None = None
        org: dict[str, Any] | None = None
        opp: dict[str, Any] | None = None
        vsum = ""

        gate_res: ExportGateResult = evaluate_export_eligibility(
            contact_email=email,
            institution_name=institution or None,
            ctx=gate_ctx,
        )
        if email:
            cont, org, opp = fetch_commercial_layers(conn, contact_email=email, org_domain=domain)
            vsum = fetch_v_commercial_queue_summaries(conn, contact_email=email, org_domain=domain)

        rec = commercial_precheck_recommendation(
            gate_eligible=gate_res.eligible,
            contact_candidate=cont,
            organization_candidate=org,
            opportunity_candidate=opp,
        )

        if rec == "keep":
            n_keep += 1
        elif rec == "review":
            n_review += 1
        else:
            n_drop += 1

        gate_reason = gate_res.reasons[0] if gate_res.reasons else ""
        (
            decision_path,
            decision_source,
            trigger_layer,
            trigger_status,
            trigger_reason_codes,
        ) = _precheck_decision_trace(
            gate_eligible=gate_res.eligible,
            gate_reason=gate_reason,
            contact_candidate=cont,
            organization_candidate=org,
            opportunity_candidate=opp,
        )

        out_rows.append(
            {
                "case_id": str(raw.get("case_id") or "").strip(),
                "contact_email": email,
                "domain": domain,
                "institution_name": institution,
                "gate_eligible": "yes" if gate_res.eligible else "no",
                "gate_reason": gate_reason,
                "contact_candidate_status": _layer_status(cont),
                "organization_candidate_status": _layer_status(org),
                "opportunity_candidate_status": _layer_status(opp),
                "contact_suppression_flags": _layer_flags(cont),
                "organization_suppression_flags": _layer_flags(org),
                "opportunity_suppression_flags": _layer_flags(opp),
                "v_commercial_candidate_queue_summary": vsum,
                "recommendation": rec,
                "decision_path": decision_path,
                "decision_source": decision_source,
                "trigger_layer": trigger_layer,
                "trigger_status": trigger_status,
                "trigger_reason_codes": trigger_reason_codes,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_fields = [
        "case_id",
        "contact_email",
        "domain",
        "institution_name",
        "gate_eligible",
        "gate_reason",
        "contact_candidate_status",
        "organization_candidate_status",
        "opportunity_candidate_status",
        "contact_suppression_flags",
        "organization_suppression_flags",
        "opportunity_suppression_flags",
        "v_commercial_candidate_queue_summary",
        "recommendation",
        "decision_path",
        "decision_source",
        "trigger_layer",
        "trigger_status",
        "trigger_reason_codes",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    return PrecheckSummary(keep=n_keep, review=n_review, drop=n_drop, rows=len(out_rows))
