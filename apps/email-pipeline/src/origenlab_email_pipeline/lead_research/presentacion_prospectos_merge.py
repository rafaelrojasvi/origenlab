"""Merge Presentación OrigenLab review CSVs into lead_research_prospect (read-only ingest)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.campaigns.presentacion_origenlab_campaign import (
    load_cyberday_sent_emails,
)
from origenlab_email_pipeline.lead_research.lead_research_builder import (
    infer_campaign_bucket,
    make_prospect_key,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import (
    ensure_lead_research_tables,
)
from origenlab_email_pipeline.leads.new_customer_research import load_exclusion_lists

BATCH_KEY_PRESENTACION = "presentacion_origenlab_2026"
SOURCE_NAME_PRESENTACION = "presentacion_origenlab_merge"

SOURCE_DEEPSEARCH = "deepsearch"
SOURCE_GMAIL = "gmail_historico"
SOURCE_FOLLOWUP = "followup_antiguo"
SOURCE_CASO_ACTIVO = "caso_activo"

CLASS_OLD_GMAIL = "old_gmail_prospect_review"
CLASS_OLD_FOLLOWUP = "old_followup_review"
CLASS_ACTIVE_HOLD = "active_case_hold"

STATUS_REVISION = "revision_individual"
STATUS_HOLD = "hold_personalizado"

_HISTORY_SENT_RE = re.compile(r"envíos=(\d+)", re.I)
_HISTORY_RECV_RE = re.compile(r"respuestas entrantes=\((\d+)\)|received=(\d+)", re.I)
_HISTORY_SUBJECT_RE = re.compile(r"Último asunto:\s*([^;]+)", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _parse_gmail_history(history_note: str) -> dict[str, Any]:
    note = history_note or ""
    sent_m = _HISTORY_SENT_RE.search(note)
    recv_m = _HISTORY_RECV_RE.search(note)
    subj_m = _HISTORY_SUBJECT_RE.search(note)
    return {
        "gmail_sent_count": int(sent_m.group(1)) if sent_m else None,
        "gmail_received_count": int(recv_m.group(1) or recv_m.group(2)) if recv_m else None,
        "gmail_latest_subject_safe": (subj_m.group(1).strip() if subj_m else None),
    }


def _existing_keys(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT prospect_key FROM lead_research_prospect WHERE is_active = 1"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _backfill_deepsearch_source_type(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        UPDATE lead_research_prospect
        SET source_type = ?, dataset_label = COALESCE(dataset_label, 'phase10b_deepsearch')
        WHERE is_active = 1
          AND (source_type IS NULL OR TRIM(source_type) = '')
        """,
        (SOURCE_DEEPSEARCH,),
    )
    return int(cur.rowcount or 0)


def _insert_prospect(
    conn: sqlite3.Connection,
    *,
    batch_id: int,
    row: dict[str, Any],
    now: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO lead_research_prospect (
          batch_id, prospect_key, organization_name, contact_name, email, domain,
          role_title, sector, region, buyer_type, likely_need, product_angle,
          evidence_url, evidence_note, source, input_priority_score, final_score,
          confidence, classification, spanish_message_angle, risk_flags,
          block_or_review_reason, recommended_next_action, status, campaign_bucket,
          is_blocked, is_active, created_at,
          source_type, dataset_label,
          gmail_first_contacted_at, gmail_last_contacted_at,
          gmail_sent_count, gmail_received_count, gmail_latest_subject_safe
        ) VALUES (
          ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
          ?,?,?,?,?,?,?
        )
        """,
        (
            batch_id,
            row["prospect_key"],
            row["organization_name"],
            row.get("contact_name"),
            row.get("email"),
            row.get("domain"),
            row.get("role_title"),
            row.get("sector"),
            row.get("region"),
            row.get("buyer_type"),
            row.get("likely_need"),
            row.get("product_angle"),
            row.get("evidence_url"),
            row.get("evidence_note"),
            row.get("source"),
            row.get("input_priority_score", 0),
            row.get("final_score", 0),
            row.get("confidence"),
            row["classification"],
            row.get("spanish_message_angle"),
            row.get("risk_flags"),
            row.get("block_or_review_reason"),
            row.get("recommended_next_action"),
            row["status"],
            row.get("campaign_bucket"),
            row.get("is_blocked", 0),
            1,
            now,
            row.get("source_type"),
            row.get("dataset_label"),
            row.get("gmail_first_contacted_at"),
            row.get("gmail_last_contacted_at"),
            row.get("gmail_sent_count"),
            row.get("gmail_received_count"),
            row.get("gmail_latest_subject_safe"),
        ),
    )
    prospect_id = int(cur.lastrowid)
    if row.get("suggested_subject") or row.get("suggested_message"):
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
                row.get("campaign_bucket"),
                row.get("spanish_message_angle"),
                row.get("recommended_next_action"),
                row.get("history_note"),
                row.get("suggested_subject"),
                row.get("suggested_message"),
                "Revisión humana requerida. No enviar automáticamente.",
            ),
        )
    return prospect_id


def _row_from_batch_csv(
    raw: dict[str, str],
    *,
    source_type: str,
    classification: str,
    status: str,
    dataset_label: str,
    is_blocked: bool = False,
    campaign_bucket: str | None = None,
) -> dict[str, Any] | None:
    em = normalize_export_email(raw.get("email") or "") or ""
    if not em:
        return None
    org = (raw.get("organization") or "").strip() or domain_of(em) or "—"
    dom = (raw.get("domain") or domain_of(em) or "").strip().lower()
    history = raw.get("history_note") or ""
    gmail = _parse_gmail_history(history)
    score = int(float(raw.get("priority_score") or 0))
    return {
        "prospect_key": make_prospect_key(org, em, dom),
        "organization_name": org,
        "contact_name": (raw.get("contact_name") or "").strip() or None,
        "email": em,
        "domain": dom,
        "sector": raw.get("sector_guess"),
        "product_angle": raw.get("product_angle"),
        "final_score": score,
        "input_priority_score": score,
        "classification": classification,
        "status": status,
        "source_type": source_type,
        "dataset_label": dataset_label,
        "spanish_message_angle": raw.get("product_angle"),
        "recommended_next_action": raw.get("reason_for_inclusion")
        or raw.get("recommended_action"),
        "block_or_review_reason": raw.get("reason_for_inclusion"),
        "history_note": history,
        "suggested_subject": raw.get("suggested_subject"),
        "suggested_message": raw.get("suggested_message"),
        "campaign_bucket": campaign_bucket or infer_campaign_bucket(classification, "", ""),
        "is_blocked": 1 if is_blocked else 0,
        "source": "gmail_archive" if source_type in (SOURCE_GMAIL, SOURCE_FOLLOWUP) else "presentacion_merge",
        **gmail,
    }


def _row_from_hold(raw: dict[str, str]) -> dict[str, Any] | None:
    em = normalize_export_email(raw.get("email") or "") or ""
    if not em:
        return None
    org = (raw.get("organization") or "").strip() or domain_of(em) or "—"
    dom = (raw.get("domain") or domain_of(em) or "").strip().lower()
    return {
        "prospect_key": make_prospect_key(org, em, dom),
        "organization_name": org,
        "contact_name": (raw.get("contact_name") or "").strip() or None,
        "email": em,
        "domain": dom,
        "classification": CLASS_ACTIVE_HOLD,
        "status": STATUS_HOLD,
        "source_type": SOURCE_CASO_ACTIVO,
        "dataset_label": "presentacion_hold_active_personalized.csv",
        "spanish_message_angle": raw.get("personalized_action"),
        "recommended_next_action": raw.get("recommended_action")
        or "hold_personalized_no_generic_campaign",
        "block_or_review_reason": raw.get("case_label"),
        "history_note": raw.get("history_note") or "",
        "suggested_subject": raw.get("suggested_subject"),
        "suggested_message": raw.get("suggested_message"),
        "campaign_bucket": "active_case",
        "is_blocked": 0,
        "final_score": 0,
        "input_priority_score": 0,
        "source": "warm_case_hold",
    }


def merge_presentacion_into_lead_research(
    conn: sqlite3.Connection,
    out_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Load presentación CSVs into lead_research_*; exclude CyberDay/bounced/suppressed."""
    out_dir = out_dir.resolve()
    cyberday = load_cyberday_sent_emails(out_dir / "cyber_production_send_log.json")
    excl = load_exclusion_lists(out_dir)
    blocked_emails = excl.bounced_emails | excl.suppressed_emails | cyberday

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for raw in _read_csv(out_dir / "presentacion_batch1_final_send_25.csv"):
        row = _row_from_batch_csv(
            raw,
            source_type=SOURCE_GMAIL,
            classification=CLASS_OLD_GMAIL,
            status=STATUS_REVISION,
            dataset_label="presentacion_batch1_final_send_25.csv",
            campaign_bucket="private_lab",
        )
        if row:
            candidates.append(row)

    for raw in _read_csv(out_dir / "presentacion_batch2_followup_old_25.csv"):
        row = _row_from_batch_csv(
            raw,
            source_type=SOURCE_FOLLOWUP,
            classification=CLASS_OLD_FOLLOWUP,
            status=STATUS_REVISION,
            dataset_label="presentacion_batch2_followup_old_25.csv",
            campaign_bucket="private_lab",
        )
        if row:
            candidates.append(row)

    for raw in _read_csv(out_dir / "presentacion_hold_active_personalized.csv"):
        row = _row_from_hold(raw)
        if row:
            candidates.append(row)

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "candidates": len(candidates),
        "cyberday_excluded": len(cyberday),
        "inserted": 0,
        "skipped_duplicate": 0,
        "skipped_blocked": 0,
    }

    if dry_run:
        for row in candidates:
            em = (row.get("email") or "").lower()
            if em in blocked_emails:
                skipped.append({"email": em, "reason": "cyberday_bounce_suppressed"})
        result["skipped_blocked"] = len(skipped)
        return result

    ensure_lead_research_tables(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    existing = _existing_keys(conn)
    now = _utc_now()

    existing_batch = conn.execute(
        "SELECT id FROM lead_research_batch WHERE batch_key = ?", (BATCH_KEY_PRESENTACION,)
    ).fetchone()
    if existing_batch:
        batch_id = int(existing_batch[0])
        conn.execute("DELETE FROM lead_research_prospect WHERE batch_id = ?", (batch_id,))
    else:
        cur = conn.execute(
            """
            INSERT INTO lead_research_batch
              (batch_key, source_name, generated_at, input_file_name, row_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                BATCH_KEY_PRESENTACION,
                SOURCE_NAME_PRESENTACION,
                now,
                "presentacion_batch*.csv",
                0,
                now,
            ),
        )
        batch_id = int(cur.lastrowid)

    inserted = 0
    for row in candidates:
        em = (row.get("email") or "").lower()
        if em in blocked_emails:
            result["skipped_blocked"] = int(result.get("skipped_blocked", 0)) + 1
            continue
        if row["prospect_key"] in existing:
            result["skipped_duplicate"] = int(result.get("skipped_duplicate", 0)) + 1
            continue
        _insert_prospect(conn, batch_id=batch_id, row=row, now=now)
        existing.add(row["prospect_key"])
        inserted += 1

    backfilled = _backfill_deepsearch_source_type(conn)
    conn.execute(
        "UPDATE lead_research_batch SET row_count = ? WHERE id = ?",
        (inserted, batch_id),
    )
    conn.commit()

    result["inserted"] = inserted
    result["backfilled_deepsearch_source_type"] = backfilled
    result["batch_id"] = batch_id
    return result
