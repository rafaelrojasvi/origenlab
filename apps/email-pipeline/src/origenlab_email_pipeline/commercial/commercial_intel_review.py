"""Minimal commercial candidate queue export and human review actions (v1).

Reads from ``v_commercial_candidate_queue``. Durable writes use
``candidate_manual_override`` and ``candidate_review_event``; the builder
re-applies active overrides after rollup sync.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Literal

from origenlab_email_pipeline.timeutil import now_iso

ReviewAction = Literal["approve", "reject", "snooze"]

_ACTION_TO_STATUS: dict[ReviewAction, str] = {
    "approve": "approved",
    "reject": "rejected",
    "snooze": "snoozed",
}

_STATUS_TO_REASON: dict[str, str] = {
    "approved": "MANUAL_APPROVE",
    "rejected": "MANUAL_REJECT",
    "snoozed": "MANUAL_SNOOZE",
}


def _entity_table(entity_kind: str) -> tuple[str, str]:
    if entity_kind == "organization":
        return "organization_candidate", "org_domain"
    if entity_kind == "contact":
        return "contact_candidate", "contact_email"
    if entity_kind == "opportunity":
        return "opportunity_candidate", "opportunity_key"
    raise ValueError(f"unknown entity_kind: {entity_kind!r}")


@dataclass(frozen=True)
class QueueFilters:
    entity_kind: str | None = None
    review_status: str | None = None
    candidate_type: str | None = None
    min_confidence: float | None = None
    min_strength: float | None = None


def fetch_queue_rows(
    conn: sqlite3.Connection,
    *,
    filters: QueueFilters | None = None,
    limit: int = 500,
    order_by: str = "confidence_score DESC, strength_score DESC",
) -> list[dict[str, Any]]:
    """Return queue rows as dicts (column names from the view)."""
    f = filters or QueueFilters()
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if f.entity_kind:
        clauses.append("entity_kind = ?")
        params.append(f.entity_kind)
    if f.review_status:
        clauses.append("status = ?")
        params.append(f.review_status)
    if f.candidate_type:
        clauses.append("candidate_type = ?")
        params.append(f.candidate_type)
    if f.min_confidence is not None:
        clauses.append("confidence_score >= ?")
        params.append(f.min_confidence)
    if f.min_strength is not None:
        clauses.append("strength_score >= ?")
        params.append(f.min_strength)

    allowed_order = {
        "confidence_score DESC, strength_score DESC",
        "strength_score DESC, confidence_score DESC",
        "updated_at DESC",
        "evidence_count DESC",
    }
    if order_by not in allowed_order:
        order_by = "confidence_score DESC, strength_score DESC"

    sql = (
        f"SELECT * FROM v_commercial_candidate_queue WHERE {' AND '.join(clauses)} "
        f"ORDER BY {order_by} LIMIT ?"
    )
    params.append(limit)

    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def export_queue_csv(rows: Iterable[dict[str, Any]]) -> str:
    row_list = list(rows)
    if not row_list:
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "entity_kind",
                "entity_key",
                "org_domain",
                "display_name",
                "candidate_type",
                "status",
                "confidence_score",
                "strength_score",
                "evidence_count",
                "latest_activity_at",
                "suppression_flags",
                "rationale_text",
                "reason_summary",
                "updated_at",
            ]
        )
        return buf.getvalue()
    keys = list(row_list[0].keys())
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    w.writerows(row_list)
    return buf.getvalue()


def export_queue_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False)


def write_export_file(path: Path, rows: list[dict[str, Any]], fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        path.write_text(export_queue_csv(rows), encoding="utf-8")
    elif fmt == "json":
        path.write_text(export_queue_json(rows), encoding="utf-8")
    else:
        raise ValueError(f"unknown format: {fmt!r}")


def apply_review_action(
    conn: sqlite3.Connection,
    *,
    entity_kind: str,
    entity_key: str,
    action: ReviewAction,
    actor: str = "human",
    note: str = "",
    run_id: int | None = None,
) -> dict[str, Any]:
    """Upsert active ``force_status`` override, update candidate row, append audit event if status changed."""
    table, key_col = _entity_table(entity_kind)
    row = conn.execute(f"SELECT status FROM {table} WHERE {key_col} = ?", (entity_key,)).fetchone()
    if row is None:
        raise ValueError(f"no candidate for {entity_kind} {entity_key!r}")

    prev_status = str(row[0])
    next_status = _ACTION_TO_STATUS[action]
    now = now_iso()
    reason_text = note.strip() or f"manual_{action}"

    existing = conn.execute(
        """
        SELECT id FROM candidate_manual_override
        WHERE entity_kind = ? AND entity_key = ? AND override_code = 'force_status' AND is_active = 1
        """,
        (entity_kind, entity_key),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE candidate_manual_override
            SET override_value = ?, reason_text = ?, actor = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_status, reason_text, actor, now, existing[0]),
        )
    else:
        conn.execute(
            """
            INSERT INTO candidate_manual_override
            (entity_kind, entity_key, override_code, override_value, reason_text, actor, is_active, created_at, updated_at)
            VALUES (?, ?, 'force_status', ?, ?, ?, 1, ?, ?)
            """,
            (entity_kind, entity_key, next_status, reason_text, actor, now, now),
        )

    conn.execute(
        f"UPDATE {table} SET status = ?, updated_at = ? WHERE {key_col} = ?",
        (next_status, now, entity_key),
    )

    event_inserted = 0
    if prev_status != next_status:
        conn.execute(
            """
            INSERT INTO candidate_review_event
            (entity_kind, entity_key, previous_status, next_status, reason_code, reason_text, note_text, actor, run_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_kind,
                entity_key,
                prev_status,
                next_status,
                _STATUS_TO_REASON[next_status],
                reason_text,
                note,
                actor,
                run_id,
                now,
            ),
        )
        event_inserted = 1

    conn.commit()
    return {
        "entity_kind": entity_kind,
        "entity_key": entity_key,
        "previous_status": prev_status,
        "next_status": next_status,
        "review_event_inserted": event_inserted,
    }
