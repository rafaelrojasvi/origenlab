"""Build SQLite lead_research_* from Phase 10B CSV outputs."""

from __future__ import annotations

import csv
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.lead_research.lead_research_schema import ensure_lead_research_tables
from origenlab_email_pipeline.leads.new_customer_research import (
    CLASS_ALREADY_CONTACTED,
    CLASS_BOUNCED,
    CLASS_NET_NEW,
    CLASS_PUBLIC_TENDER,
    CLASS_RESEARCH_ONLY,
    CLASS_SAME_DOMAIN,
    CLASS_SUPPLIER_INTERNAL,
    CLASS_SUPPRESSED,
    REVIEW_OUTPUT_FIELDS,
)

_BLOCKED_CLASSIFICATIONS = frozenset(
    {
        CLASS_ALREADY_CONTACTED,
        CLASS_BOUNCED,
        CLASS_SUPPRESSED,
        CLASS_SUPPLIER_INTERNAL,
    }
)

_CLASSIFICATION_TO_STATUS: dict[str, str] = {
    CLASS_NET_NEW: "net_new_safe_review",
    CLASS_SAME_DOMAIN: "same_domain_review",
    CLASS_PUBLIC_TENDER: "public_tender_review",
    CLASS_RESEARCH_ONLY: "research_needed",
    CLASS_ALREADY_CONTACTED: "blocked",
    CLASS_BOUNCED: "blocked",
    CLASS_SUPPRESSED: "blocked",
    CLASS_SUPPLIER_INTERNAL: "blocked",
}

_DEFAULT_REVIEW_DIR = Path("reports/out/active/current")
_REVIEW_CSV = "new_customer_targets_review.csv"
_BLOCKED_CSV = "new_customer_targets_blocked.csv"
_FOLLOWUP_CSV = "follow_up_candidates_review.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_prospect_key(organization_name: str, email: str, domain: str) -> str:
    seed = (email or "").strip().lower() or f"{organization_name.strip().lower()}|{(domain or '').strip().lower()}"
    slug = re.sub(r"[^a-z0-9]+", "-", seed).strip("-")
    if len(slug) >= 8:
        return slug[:120]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    org_bit = re.sub(r"[^a-z0-9]+", "-", organization_name.lower()).strip("-")[:40]
    return f"{org_bit}-{digest}" if org_bit else digest


def infer_campaign_bucket(classification: str, sector: str, buyer_type: str) -> str:
    buyer = (buyer_type or "").lower()
    if classification == CLASS_PUBLIC_TENDER or "public_tender" in buyer:
        return "public_tender"
    if classification == CLASS_SAME_DOMAIN:
        return "same_domain"
    if "universidad" in (sector or "").lower() or "centro_investigacion" in buyer:
        return "university"
    if any(
        x in buyer
        for x in (
            "laboratorio_privado",
            "laboratorio_alimentos",
            "laboratorio_acuicola",
            "laboratorio_agua",
        )
    ):
        return "private_lab"
    if "laboratorio" in buyer or "centro_ensayos" in buyer:
        return "private_lab"
    return "other"


def classification_to_status(classification: str) -> str:
    return _CLASSIFICATION_TO_STATUS.get(classification, "review_only")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _blocked_recommended_action(classification: str, row: dict[str, str]) -> str:
    explicit = (row.get("recommended_next_action") or "").strip()
    if explicit:
        return explicit
    if classification == CLASS_ALREADY_CONTACTED:
        return "No contactar: ya contactado"
    return "No contactar — bloqueado por historial OrigenLab"


def _parse_phase10b_row(row: dict[str, str], *, from_blocked_csv: bool) -> dict[str, Any]:
    classification = (row.get("classification") or "").strip()
    is_blocked = classification in _BLOCKED_CLASSIFICATIONS
    status = "blocked" if is_blocked else classification_to_status(classification)
    sector = (row.get("sector") or "").strip()
    buyer_type = (row.get("buyer_type") or "").strip()
    org = (row.get("organization_name") or "").strip()
    email = (row.get("email") or "").strip()
    domain = (row.get("domain") or "").strip()
    likely_need = (row.get("likely_need") or row.get("product_angle") or "").strip()
    block_or_review = (
        (row.get("block_reason") if from_blocked_csv else row.get("block_or_review_reason")) or ""
    ).strip()
    return {
        "prospect_key": make_prospect_key(org, email, domain),
        "organization_name": org,
        "contact_name": (row.get("contact_name") or "").strip() or None,
        "email": email or None,
        "domain": domain or None,
        "role_title": None,
        "sector": sector or None,
        "region": (row.get("region") or "").strip() or None,
        "buyer_type": buyer_type or None,
        "likely_need": likely_need or None,
        "product_angle": (row.get("product_angle") or "").strip() or None,
        "evidence_url": (row.get("evidence_url") or "").strip() or None,
        "evidence_note": (row.get("evidence_note") or "").strip() or None,
        "source": (row.get("source") or "").strip() or None,
        "input_priority_score": int(row.get("input_priority_score") or 0),
        "final_score": int(row.get("final_score") or 0),
        "confidence": (row.get("confidence") or "").strip() or None,
        "classification": classification,
        "spanish_message_angle": (row.get("spanish_message_angle") or "").strip() or None,
        "risk_flags": (row.get("risk_flags") or "").strip() or None,
        "block_or_review_reason": block_or_review or None,
        "recommended_next_action": _blocked_recommended_action(classification, row)
        if is_blocked
        else (row.get("recommended_next_action") or "").strip() or None,
        "status": status,
        "campaign_bucket": infer_campaign_bucket(classification, sector, buyer_type),
        "is_blocked": 1 if is_blocked else 0,
    }


def _parse_review_row(row: dict[str, str]) -> dict[str, Any]:
    return _parse_phase10b_row(row, from_blocked_csv=False)


def _parse_blocked_row(row: dict[str, str]) -> dict[str, Any]:
    return _parse_phase10b_row(row, from_blocked_csv=True)


def _suggested_subject(org: str, product_angle: str | None) -> str:
    angle = (product_angle or "equipamiento de laboratorio").split(";")[0].strip()
    return f"Consulta técnica — {org} — {angle}"


def _suggested_body_preview(org: str, spanish_angle: str | None) -> str:
    angle = spanish_angle or "equipos y reactivos para su laboratorio"
    return (
        f"Estimados/as equipo de {org},\n\n"
        f"En OrigenLab apoyamos laboratorios con {angle}. "
        "¿Le acomoda una breve llamada para entender su necesidad actual?\n\n"
        "Saludos cordiales,\nOrigenLab"
    )


def _block_reason_rows(prospect: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    classification = prospect.get("classification") or ""
    if classification in _BLOCKED_CLASSIFICATIONS:
        labels = {
            CLASS_ALREADY_CONTACTED: "Ya contactado",
            CLASS_BOUNCED: "Rebote",
            CLASS_SUPPRESSED: "Suprimido",
            CLASS_SUPPLIER_INTERNAL: "Proveedor o interno",
        }
        out.append((classification, labels.get(classification, classification)))
    reason = prospect.get("block_or_review_reason") or ""
    if reason and not out:
        out.append(("review_reason", reason))
    for flag in (prospect.get("risk_flags") or "").split(","):
        flag = flag.strip()
        if flag:
            out.append((flag, flag.replace("_", " ")))
    return out


def build_lead_research_sqlite(
    conn: sqlite3.Connection,
    *,
    review_csv: Path,
    blocked_csv: Path,
    followup_csv: Path | None = None,
    batch_key: str = "phase10b_current",
    source_name: str = "deepsearch_phase10b",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Load Phase 10B CSVs into lead_research_* tables (idempotent per batch_key)."""
    review_rows = _read_csv_rows(review_csv)
    blocked_rows = _read_csv_rows(blocked_csv)
    prospects = [_parse_review_row(r) for r in review_rows] + [_parse_blocked_row(r) for r in blocked_rows]

    counts = {
        "prospects_review": sum(1 for p in prospects if not p["is_blocked"]),
        "prospects_blocked": sum(1 for p in prospects if p["is_blocked"]),
        "net_new_safe": sum(1 for p in prospects if p["classification"] == CLASS_NET_NEW),
        "public_tender_review": sum(1 for p in prospects if p["classification"] == CLASS_PUBLIC_TENDER),
        "same_domain_review": sum(1 for p in prospects if p["classification"] == CLASS_SAME_DOMAIN),
        "research_needed": sum(1 for p in prospects if p["classification"] == CLASS_RESEARCH_ONLY),
    }

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "batch_key": batch_key,
        "review_csv": str(review_csv),
        "blocked_csv": str(blocked_csv),
        "row_count": len(prospects),
        **counts,
    }

    if dry_run:
        return result

    ensure_lead_research_tables(conn)
    now = _utc_now()
    conn.execute("PRAGMA foreign_keys = ON")

    existing = conn.execute(
        "SELECT id FROM lead_research_batch WHERE batch_key = ?", (batch_key,)
    ).fetchone()
    if existing:
        batch_id = int(existing[0])
        conn.execute("DELETE FROM lead_research_prospect WHERE batch_id = ?", (batch_id,))
        conn.execute("DELETE FROM lead_research_followup_candidate WHERE batch_id = ?", (batch_id,))
        conn.execute(
            """
            UPDATE lead_research_batch
            SET source_name = ?, generated_at = ?, input_file_name = ?, row_count = ?
            WHERE id = ?
            """,
            (source_name, now, review_csv.name, len(prospects), batch_id),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO lead_research_batch
              (batch_key, source_name, generated_at, input_file_name, row_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (batch_key, source_name, now, review_csv.name, len(prospects), now),
        )
        batch_id = int(cur.lastrowid)

    for p in prospects:
        cur = conn.execute(
            """
            INSERT INTO lead_research_prospect (
              batch_id, prospect_key, organization_name, contact_name, email, domain,
              role_title, sector, region, buyer_type, likely_need, product_angle,
              evidence_url, evidence_note, source, input_priority_score, final_score,
              confidence, classification, spanish_message_angle, risk_flags,
              block_or_review_reason, recommended_next_action, status, campaign_bucket,
              is_blocked, is_active, created_at
            ) VALUES (
              ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            (
                batch_id,
                p["prospect_key"],
                p["organization_name"],
                p["contact_name"],
                p["email"],
                p["domain"],
                p["role_title"],
                p["sector"],
                p["region"],
                p["buyer_type"],
                p["likely_need"],
                p["product_angle"],
                p["evidence_url"],
                p["evidence_note"],
                p["source"],
                p["input_priority_score"],
                p["final_score"],
                p["confidence"],
                p["classification"],
                p["spanish_message_angle"],
                p["risk_flags"],
                p["block_or_review_reason"],
                p["recommended_next_action"],
                p["status"],
                p["campaign_bucket"],
                p["is_blocked"],
                1,
                now,
            ),
        )
        prospect_id = int(cur.lastrowid)
        if p.get("evidence_url") or p.get("evidence_note"):
            conn.execute(
                """
                INSERT INTO lead_research_evidence
                  (prospect_id, evidence_kind, evidence_url, evidence_note, source, confidence)
                VALUES (?, 'public_url', ?, ?, ?, ?)
                """,
                (
                    prospect_id,
                    p.get("evidence_url"),
                    p.get("evidence_note"),
                    p.get("source"),
                    p.get("confidence"),
                ),
            )
        why = p.get("likely_need") or ""
        if p.get("product_angle"):
            why = f"{why} · {p['product_angle']}".strip(" ·")
        safety_note = (
            "No contactar — bloqueado por historial OrigenLab."
            if p["is_blocked"]
            else "Revisión humana requerida. No enviar automáticamente."
        )
        conn.execute(
            """
            INSERT INTO lead_research_recommendation (
              prospect_id, campaign_bucket, recommended_message_angle,
              recommended_next_action, why_this_lead, suggested_subject,
              suggested_body_preview, safety_note
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                prospect_id,
                p["campaign_bucket"],
                p.get("spanish_message_angle"),
                p.get("recommended_next_action"),
                why or None,
                _suggested_subject(p["organization_name"], p.get("product_angle")),
                _suggested_body_preview(p["organization_name"], p.get("spanish_message_angle")),
                safety_note,
            ),
        )
        for code, label in _block_reason_rows(p):
            conn.execute(
                """
                INSERT INTO lead_research_block_reason (prospect_id, reason_code, reason_label)
                VALUES (?, ?, ?)
                """,
                (prospect_id, code, label),
            )

    if followup_csv and followup_csv.is_file():
        for row in _read_csv_rows(followup_csv):
            email = (row.get("normalized_email") or row.get("email") or "").strip().lower()
            if not email:
                continue
            conn.execute(
                """
                INSERT INTO lead_research_followup_candidate (
                  batch_id, normalized_email, organization_name, domain,
                  last_contacted_at, latest_subject_safe, recommended_follow_up_angle, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    batch_id,
                    email,
                    (row.get("organization_name") or "").strip() or None,
                    (row.get("domain") or "").strip() or None,
                    (row.get("last_contacted_at") or "").strip() or None,
                    (row.get("latest_subject_safe") or row.get("latest_subject") or "").strip() or None,
                    (row.get("recommended_follow_up_angle") or "").strip() or None,
                    now,
                ),
            )

    conn.commit()
    result["batch_id"] = batch_id
    return result


def sqlite_lead_research_counts(conn: sqlite3.Connection) -> dict[str, int]:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_research_prospect'"
    ).fetchone():
        return {
            "prospects": 0,
            "evidence": 0,
            "recommendations": 0,
            "block_reasons": 0,
        }
    def _c(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0

    return {
        "prospects": _c("SELECT COUNT(*) FROM lead_research_prospect WHERE is_active = 1"),
        "evidence": _c("SELECT COUNT(*) FROM lead_research_evidence"),
        "recommendations": _c("SELECT COUNT(*) FROM lead_research_recommendation"),
        "block_reasons": _c("SELECT COUNT(*) FROM lead_research_block_reason"),
    }


def default_phase10b_paths(repo_root: Path) -> tuple[Path, Path, Path]:
    base = repo_root / "apps/email-pipeline" / _DEFAULT_REVIEW_DIR
    return (
        base / _REVIEW_CSV,
        base / _BLOCKED_CSV,
        base / _FOLLOWUP_CSV,
    )
