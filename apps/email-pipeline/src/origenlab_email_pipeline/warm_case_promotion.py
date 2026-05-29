"""Promote SQLite cases_review_queue rows into Postgres commercial.warm_case* (DB-2B)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.cases_review_queue import fetch_cases_review_queue
from origenlab_email_pipeline.mart_core_postgres_migrate import (
    connect_sqlite_readonly,
    iso_text_to_datetime,
    normalize_postgres_url,
)
from origenlab_email_pipeline.warm_case_grouping import thread_case_hint
from origenlab_email_pipeline.warm_case_classification import (
    WarmCaseCategory,
    account_name_from_sender,
    contact_email_from_sender,
    equipment_signal_text,
    infer_next_action,
    infer_warm_case_category,
    infer_warm_case_status,
)
from origenlab_email_pipeline.warm_case_role_classification import _is_sent_folder
from origenlab_email_pipeline.warm_case_sender_rules import contact_email_from_recipients

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Json = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

PROMOTION_SOURCE = "warm_queue_promotion"
_FORBIDDEN_ROW_KEYS = frozenset(
    {"body", "body_html", "body_text_raw", "body_text_clean", "full_body_clean", "top_reply_clean", "raw_json"}
)


@dataclass(frozen=True)
class WarmCasePromotionRecord:
    case_key: str
    title: str
    account_name: str
    primary_contact_email: str
    primary_domain: str | None
    category: WarmCaseCategory
    status: str
    next_action: str
    equipment_signal: str | None
    last_email_id: int
    last_activity_at: datetime


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def build_case_key(
    primary_contact_email: str, primary_domain: str | None, *, thread_hint: str | None = None
) -> str:
    if thread_hint and thread_hint.strip():
        digest = hashlib.sha256(thread_hint.strip().lower().encode("utf-8")).hexdigest()
        return f"warm:thread:{digest}"
    email = primary_contact_email.strip().lower()
    domain = (primary_domain or "").strip().lower()
    digest = hashlib.sha256(f"{email}|{domain}".encode("utf-8")).hexdigest()
    return f"warm:{digest}"


def _primary_domain(contact_email: str) -> str | None:
    if "@" not in contact_email:
        return None
    return contact_email.split("@", 1)[1].lower() or None


def _thread_case_hint(subject: str, contact_email: str = "") -> str | None:
    return thread_case_hint(subject, contact_email)


def _promotion_title(subject: str, category: WarmCaseCategory) -> str:
    sub = (subject or "").lower()
    if ("rv10.70" in sub or "3812200" in sub) and "rg energia" in sub:
        return "RG Energía — IKA RV10.70 tubo vapor — qty 3"
    if ("unach" in sub or "universidad adventista" in sub) and (
        "hielscher" in sub or "uip2000" in sub
    ):
        return "UNACH — Hielscher UIP2000hdT — extracción vegetal"
    if ("crtop" in sub or "reactor" in sub or "olt-hp-5l" in sub) and category == "supplier_reply":
        if any(cue in sub for cue in ("shipping", "flete", "address")):
            return "CRTOP — Reactor OLT-HP-5L — flete pendiente"
        return "CRTOP — Reactor OLT-HP-5L — cotización recibida"
    if "ongo" in sub and category == "quote_sent":
        return "ONGO — Cotización UP400St enviada"
    return subject[:500]


def _promotion_account_name(
    sender: str, contact_email: str, subject: str, category: WarmCaseCategory
) -> str:
    sub = (subject or "").lower()
    if ("rv10.70" in sub or "3812200" in sub) and "rg energia" in sub:
        return "RG ENERGIA SPA"
    if ("crtop" in sub or "reactor" in sub) and category == "supplier_reply":
        return "CRTOP"
    if "unach" in sub or "universidad adventista" in sub:
        return "Universidad Adventista de Chile (UNACH)"
    if "ongo" in sub or contact_email.endswith("@ongo.cl"):
        return "ONGO"
    return account_name_from_sender(sender, contact_email)


def _activity_at_from_row(row: dict[str, Any]) -> datetime:
    parsed = iso_text_to_datetime(row.get("date_iso"))
    return parsed if parsed is not None else datetime.now(timezone.utc)


def queue_row_to_promotion_record(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool = True,
) -> WarmCasePromotionRecord | None:
    if _FORBIDDEN_ROW_KEYS.intersection(row.keys()):
        raise ValueError("queue row must not include raw email body fields")

    source_file = str(row.get("source_file") or "")
    if _is_sent_folder(source_file):
        contact_email = contact_email_from_recipients(
            row.get("recipients_preview")
            if isinstance(row.get("recipients_preview"), str)
            else row.get("recipients")
            if isinstance(row.get("recipients"), str)
            else None
        )
    else:
        contact_email = contact_email_from_sender(
            row.get("sender_preview") if isinstance(row.get("sender_preview"), str) else None
        )
    contact_email = contact_email.strip().lower()
    if not contact_email or "@" not in contact_email:
        return None

    subject = str(row.get("subject_preview") or "").strip() or "(sin asunto)"
    sender = str(row.get("sender_preview") or "")
    category = infer_warm_case_category(
        row,
        enrichment_available=enrichment_available,
        include_noise=include_noise,
    )
    status = infer_warm_case_status(category, row)
    domain = _primary_domain(contact_email)
    equip = equipment_signal_text(subject, row, enrichment_available=enrichment_available) or None

    thread_hint = _thread_case_hint(subject, contact_email)

    return WarmCasePromotionRecord(
        case_key=build_case_key(contact_email, domain, thread_hint=thread_hint),
        title=_promotion_title(subject, category),
        account_name=_promotion_account_name(sender, contact_email, subject, category),
        primary_contact_email=contact_email,
        primary_domain=domain,
        category=category,
        status=status,
        next_action=infer_next_action(category, row=row),
        equipment_signal=equip,
        last_email_id=int(row["email_id"]),
        last_activity_at=_activity_at_from_row(row),
    )


def dedupe_candidates(records: list[WarmCasePromotionRecord]) -> dict[str, WarmCasePromotionRecord]:
    """One case per case_key; keep the row with the latest activity."""
    by_key: dict[str, WarmCasePromotionRecord] = {}
    for rec in sorted(records, key=lambda r: r.last_activity_at):
        by_key[rec.case_key] = rec
    return by_key


def load_candidates_from_sqlite(
    sqlite_path: Path,
    *,
    days_window: int = 30,
    exclude_obvious_noise: bool = True,
    limit: int = 200,
) -> tuple[dict[str, WarmCasePromotionRecord], dict[str, Any]]:
    conn = connect_sqlite_readonly(sqlite_path)
    try:
        queue = fetch_cases_review_queue(
            conn,
            days_window=days_window,
            exclude_obvious_noise=exclude_obvious_noise,
            limit=limit,
        )
        records: list[WarmCasePromotionRecord] = []
        for row in queue.rows:
            rec = queue_row_to_promotion_record(
                row,
                enrichment_available=queue.enrichment_available,
            )
            if rec is not None:
                records.append(rec)
        deduped = dedupe_candidates(records)
        meta = {
            "queue_row_count": len(queue.rows),
            "enrichment_available": queue.enrichment_available,
            "reduced_mode": queue.reduced_mode,
            "caption_es": queue.caption_es,
        }
        return deduped, meta
    finally:
        conn.close()


def _categories_summary(candidates: dict[str, WarmCasePromotionRecord]) -> dict[str, int]:
    return dict(Counter(rec.category for rec in candidates.values()))


def preview_promotion(
    sqlite_path: Path,
    *,
    days_window: int = 30,
    exclude_obvious_noise: bool = True,
    limit: int = 200,
    pg_url: str | None = None,
) -> dict[str, Any]:
    candidates, queue_meta = load_candidates_from_sqlite(
        sqlite_path,
        days_window=days_window,
        exclude_obvious_noise=exclude_obvious_noise,
        limit=limit,
    )
    would_insert = len(candidates)
    would_update = 0
    if pg_url and candidates:
        _require_psycopg()
        assert psycopg is not None
        keys = list(candidates.keys())
        with psycopg.connect(normalize_postgres_url(pg_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT case_key FROM commercial.warm_case
                    WHERE case_key = ANY(%s)
                    """,
                    (keys,),
                )
                existing = {str(row[0]) for row in cur.fetchall()}
        would_update = sum(1 for k in candidates if k in existing)
        would_insert = len(candidates) - would_update

    sample_keys = list(candidates.keys())[:5]
    return {
        "dry_run": True,
        "applied": False,
        "candidate_count": len(candidates),
        "would_insert_cases": would_insert,
        "would_update_cases": would_update,
        "would_link_emails": len(candidates),
        "sample_case_keys": sample_keys,
        "categories_summary": _categories_summary(candidates),
        **queue_meta,
    }


def _lookup_case(cur: Any, case_key: str) -> tuple[int, str] | None:
    cur.execute(
        "SELECT id, status FROM commercial.warm_case WHERE case_key = %s",
        (case_key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return int(row[0]), str(row[1])


def _should_write_equipment_signal(rec: WarmCasePromotionRecord) -> bool:
    return rec.category == "opportunity" or bool((rec.equipment_signal or "").strip())


def apply_promotion(
    pg_url: str,
    sqlite_path: Path,
    *,
    days_window: int = 30,
    exclude_obvious_noise: bool = True,
    limit: int = 200,
    updated_by: str,
    reason: str,
) -> dict[str, Any]:
    _require_psycopg()
    assert psycopg is not None and Json is not None

    candidates, queue_meta = load_candidates_from_sqlite(
        sqlite_path,
        days_window=days_window,
        exclude_obvious_noise=exclude_obvious_noise,
        limit=limit,
    )

    summary: dict[str, Any] = {
        "dry_run": False,
        "applied": False,
        "candidate_count": len(candidates),
        "inserted_cases": 0,
        "updated_cases": 0,
        "linked_emails": 0,
        "status_history_rows": 0,
        "events_inserted": 0,
        "equipment_signals_upserted": 0,
        "updated_by": updated_by,
        "reason": reason,
        "categories_summary": _categories_summary(candidates),
        **queue_meta,
    }

    if not candidates:
        summary["warning"] = "no_candidates"
        return summary

    pg_url_norm = normalize_postgres_url(pg_url)

    with psycopg.connect(pg_url_norm, autocommit=False) as conn:
        with conn.cursor() as cur:
            for rec in candidates.values():
                existing = _lookup_case(cur, rec.case_key)
                is_insert = existing is None

                cur.execute(
                    """
                    INSERT INTO commercial.warm_case (
                      case_key, title, account_name, primary_contact_email, primary_domain,
                      category, status, next_action, equipment_signal,
                      last_activity_at, last_email_id, source, updated_by
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (case_key) DO UPDATE SET
                      title = EXCLUDED.title,
                      account_name = EXCLUDED.account_name,
                      primary_contact_email = EXCLUDED.primary_contact_email,
                      primary_domain = EXCLUDED.primary_domain,
                      category = EXCLUDED.category,
                      status = EXCLUDED.status,
                      next_action = EXCLUDED.next_action,
                      equipment_signal = EXCLUDED.equipment_signal,
                      last_activity_at = GREATEST(
                        commercial.warm_case.last_activity_at, EXCLUDED.last_activity_at
                      ),
                      last_email_id = EXCLUDED.last_email_id,
                      updated_at = now(),
                      updated_by = EXCLUDED.updated_by
                    RETURNING id, status
                    """,
                    (
                        rec.case_key,
                        rec.title,
                        rec.account_name,
                        rec.primary_contact_email,
                        rec.primary_domain,
                        rec.category,
                        rec.status,
                        rec.next_action,
                        rec.equipment_signal,
                        rec.last_activity_at,
                        rec.last_email_id,
                        PROMOTION_SOURCE,
                        updated_by,
                    ),
                )
                row = cur.fetchone()
                case_id = int(row[0])
                new_status = str(row[1])
                old_status = existing[1] if existing else None

                if is_insert:
                    summary["inserted_cases"] += 1
                else:
                    summary["updated_cases"] += 1

                if old_status != new_status:
                    cur.execute(
                        """
                        INSERT INTO commercial.warm_case_status_history (
                          case_id, from_status, to_status, reason, changed_by
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (case_id, old_status, new_status, reason, updated_by),
                    )
                    summary["status_history_rows"] += 1

                cur.execute(
                    """
                    INSERT INTO commercial.warm_case_linked_email (
                      case_id, email_id, link_role, linked_by
                    ) VALUES (%s, %s, 'thread', %s)
                    ON CONFLICT (case_id, email_id) DO NOTHING
                    RETURNING case_id
                    """,
                    (case_id, rec.last_email_id, updated_by),
                )
                if cur.fetchone():
                    summary["linked_emails"] += 1

                if is_insert:
                    cur.execute(
                        """
                        INSERT INTO commercial.warm_case_event (
                          case_id, event_type, payload_json, created_by
                        ) VALUES (%s, 'promote', %s, %s)
                        """,
                        (
                            case_id,
                            Json(
                                {
                                    "email_id": rec.last_email_id,
                                    "reason": reason,
                                    "case_key": rec.case_key,
                                }
                            ),
                            updated_by,
                        ),
                    )
                    summary["events_inserted"] += 1

                if _should_write_equipment_signal(rec):
                    cur.execute(
                        """
                        INSERT INTO commercial.warm_case_equipment_signal (
                          case_id, equipment_category, details_json
                        ) VALUES (%s, %s, %s)
                        ON CONFLICT (case_id) DO UPDATE SET
                          equipment_category = EXCLUDED.equipment_category,
                          details_json = EXCLUDED.details_json
                        """,
                        (
                            case_id,
                            (rec.equipment_signal or rec.category)[:120],
                            Json({"source": PROMOTION_SOURCE, "category": rec.category}),
                        ),
                    )
                    summary["equipment_signals_upserted"] += 1

        conn.commit()

    summary["applied"] = True
    return summary
