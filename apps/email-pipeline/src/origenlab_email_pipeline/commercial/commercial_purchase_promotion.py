"""Find Gmail source rows and promote confirmed purchase orders into SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of, emails_in, primary_sender_email
from origenlab_email_pipeline.commercial.ceaf_oc_26172 import (
    CEAF_BUYER_DOMAIN,
    CEAF_OC_NUMBER,
    CEAF_SUBJECT_FRAGMENT,
    ceaf_oc_26172_event_fields,
    ceaf_oc_26172_expected_attachment_filenames,
    ceaf_oc_26172_line_items,
)
from origenlab_email_pipeline.commercial.commercial_purchase_schema import (
    ensure_commercial_purchase_tables,
)
from origenlab_email_pipeline.timeutil import now_iso

INGEST_HINT = """
Source email not found in SQLite. Run Gmail ingest first, then retry promotion:

  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder INBOX --skip-duplicate-message-id
  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados" --skip-duplicate-message-id
""".strip()


@dataclass(frozen=True)
class MatchedEmail:
    id: int
    message_id: str | None
    source_file: str | None
    subject: str | None
    sender: str | None
    recipients: str | None
    date_iso: str | None
    folder: str | None


@dataclass(frozen=True)
class MatchedAttachment:
    id: int
    email_id: int
    filename: str
    content_type: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class PromotionPlan:
    email: MatchedEmail
    attachments: list[MatchedAttachment]
    event_fields: dict[str, Any]
    line_items: list[dict[str, Any]]
    existing_event_id: int | None
    action: str  # insert | update


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _row_to_email(row: sqlite3.Row) -> MatchedEmail:
    return MatchedEmail(
        id=int(row["id"]),
        message_id=row["message_id"],
        source_file=row["source_file"],
        subject=row["subject"],
        sender=row["sender"],
        recipients=row["recipients"],
        date_iso=row["date_iso"],
        folder=row["folder"] if "folder" in row.keys() else None,
    )


def find_source_email(
    conn: sqlite3.Connection,
    *,
    subject: str | None = None,
    oc_number: str | None = None,
    buyer_domain: str | None = None,
) -> MatchedEmail | None:
    """Locate the inbound OC email in SQLite (read-only)."""
    if not _table_exists(conn, "emails"):
        return None

    oc = (oc_number or "").strip()
    dom = (buyer_domain or "").strip().lower().lstrip("@")
    subj = (subject or "").strip()

    queries: list[tuple[str, tuple[Any, ...]]] = []

    if subj:
        queries.append(
            (
                """
                SELECT id, message_id, source_file, subject, sender, recipients, date_iso, folder
                FROM emails
                WHERE subject = ?
                ORDER BY date_iso DESC
                LIMIT 1
                """,
                (subj,),
            )
        )
        queries.append(
            (
                """
                SELECT id, message_id, source_file, subject, sender, recipients, date_iso, folder
                FROM emails
                WHERE subject LIKE ?
                ORDER BY date_iso DESC
                LIMIT 1
                """,
                (f"%{subj}%",),
            )
        )

    if oc:
        queries.append(
            (
                """
                SELECT id, message_id, source_file, subject, sender, recipients, date_iso, folder
                FROM emails
                WHERE subject LIKE ?
                ORDER BY date_iso DESC
                LIMIT 1
                """,
                (f"%{oc}%",),
            )
        )
        if _table_exists(conn, "attachments"):
            queries.append(
                (
                    """
                    SELECT e.id, e.message_id, e.source_file, e.subject, e.sender,
                           e.recipients, e.date_iso, e.folder
                    FROM emails e
                    JOIN attachments a ON a.email_id = e.id
                    WHERE a.filename LIKE ?
                    ORDER BY e.date_iso DESC
                    LIMIT 1
                    """,
                    (f"%{oc}%",),
                )
            )

    if dom:
        queries.append(
            (
                """
                SELECT id, message_id, source_file, subject, sender, recipients, date_iso, folder
                FROM emails
                WHERE LOWER(sender) LIKE ?
                ORDER BY date_iso DESC
                LIMIT 1
                """,
                (f"%@{dom}%",),
            )
        )

    queries.append(
        (
            """
            SELECT id, message_id, source_file, subject, sender, recipients, date_iso, folder
            FROM emails
            WHERE subject LIKE '%Remite OC%'
              AND LOWER(sender) LIKE '%ceaf%'
            ORDER BY date_iso DESC
            LIMIT 1
            """,
            (),
        )
    )

    conn.row_factory = sqlite3.Row
    for sql, params in queries:
        row = conn.execute(sql, params).fetchone()
        if row:
            return _row_to_email(row)
    return None


def find_email_attachments(
    conn: sqlite3.Connection,
    email_id: int,
    *,
    expected_filenames: tuple[str, ...] | None = None,
) -> list[MatchedAttachment]:
    if not _table_exists(conn, "attachments"):
        return []
    rows = conn.execute(
        """
        SELECT id, email_id, filename, content_type, size_bytes
        FROM attachments
        WHERE email_id = ?
        ORDER BY part_index, id
        """,
        (email_id,),
    ).fetchall()
    out = [
        MatchedAttachment(
            id=int(r[0]),
            email_id=int(r[1]),
            filename=str(r[2] or ""),
            content_type=r[3],
            size_bytes=int(r[4]) if r[4] is not None else None,
        )
        for r in rows
    ]
    if expected_filenames:
        expected_lower = {f.lower() for f in expected_filenames}
        matched = [a for a in out if a.filename.lower() in expected_lower]
        if matched:
            return matched
    return out


def _existing_event_id(
    conn: sqlite3.Connection,
    *,
    source_email_id: int,
    oc_number: str,
    buyer_org_name: str,
) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM commercial_purchase_events
        WHERE source_email_id = ? AND oc_number = ?
        LIMIT 1
        """,
        (source_email_id, oc_number),
    ).fetchone()
    if row:
        return int(row[0])
    row = conn.execute(
        """
        SELECT id FROM commercial_purchase_events
        WHERE buyer_org_name = ? AND oc_number = ?
        LIMIT 1
        """,
        (buyer_org_name, oc_number),
    ).fetchone()
    return int(row[0]) if row else None


def build_ceaf_oc_26172_plan(conn: sqlite3.Connection) -> PromotionPlan:
    email = find_source_email(
        conn,
        subject=CEAF_SUBJECT_FRAGMENT,
        oc_number=CEAF_OC_NUMBER,
        buyer_domain=CEAF_BUYER_DOMAIN,
    )
    if email is None:
        raise FileNotFoundError(INGEST_HINT)

    attachments = find_email_attachments(
        conn,
        email.id,
        expected_filenames=ceaf_oc_26172_expected_attachment_filenames(),
    )
    event_fields = ceaf_oc_26172_event_fields()
    event_fields.update(_email_link_fields(email))
    existing_id = None
    if _table_exists(conn, "commercial_purchase_events"):
        existing_id = _existing_event_id(
            conn,
            source_email_id=email.id,
            oc_number=CEAF_OC_NUMBER,
            buyer_org_name=str(event_fields["buyer_org_name"]),
        )
    return PromotionPlan(
        email=email,
        attachments=attachments,
        event_fields=event_fields,
        line_items=ceaf_oc_26172_line_items(),
        existing_event_id=existing_id,
        action="update" if existing_id else "insert",
    )


def _email_link_fields(email: MatchedEmail) -> dict[str, Any]:
    to_addrs = emails_in(email.recipients or "")
    return {
        "source_email_id": email.id,
        "source_message_id": email.message_id,
        "source_file": email.source_file,
        "email_subject": email.subject,
        "email_from": email.sender,
        "email_to": "; ".join(to_addrs) if to_addrs else email.recipients,
        "email_date_iso": email.date_iso,
    }


def _attachment_document_type(filename: str) -> str:
    low = filename.lower()
    if "oc" in low or "orden" in low:
        return "purchase_order"
    if "cn" in low or "cotiz" in low or "presup" in low:
        return "quotation"
    return "other"


def apply_promotion_plan(conn: sqlite3.Connection, plan: PromotionPlan) -> int:
    """Write event + items + attachments (idempotent upsert)."""
    ensure_commercial_purchase_tables(conn)
    now = now_iso()
    ev = plan.event_fields
    evidence = {
        "promotion": "ceaf_oc_26172",
        "source_email_id": plan.email.id,
        "attachment_ids": [a.id for a in plan.attachments],
        "attachment_filenames": [a.filename for a in plan.attachments],
    }
    cols = [
        "source_email_id",
        "source_message_id",
        "source_file",
        "email_subject",
        "email_from",
        "email_to",
        "email_date_iso",
        "buyer_org_name",
        "buyer_rut",
        "buyer_contact_name",
        "buyer_contact_role",
        "buyer_contact_email",
        "buyer_domain",
        "purchase_status",
        "oc_number",
        "oc_date",
        "quote_number",
        "quote_date",
        "project_name",
        "project_code",
        "project_responsible",
        "associated_line",
        "net_amount_clp",
        "iva_amount_clp",
        "gross_amount_clp",
        "currency",
        "payment_terms",
        "delivery_address",
        "invoice_email",
        "invoice_cc_email",
        "dispatch_requested",
        "invoice_requested",
        "bank_details_requested",
        "commercial_summary",
        "confidence",
    ]
    values = [ev.get(c) for c in cols]
    evidence_json = json.dumps(evidence, ensure_ascii=False)

    if plan.existing_event_id:
        event_id = plan.existing_event_id
        update_cols = [*cols, "evidence_json", "updated_at"]
        set_clause = ", ".join(f"{c}=?" for c in update_cols)
        conn.execute(
            f"UPDATE commercial_purchase_events SET {set_clause} WHERE id=?",
            (*values, evidence_json, now, event_id),
        )
        conn.execute(
            "DELETE FROM commercial_purchase_event_items WHERE purchase_event_id=?",
            (event_id,),
        )
        conn.execute(
            "DELETE FROM commercial_purchase_event_attachments WHERE purchase_event_id=?",
            (event_id,),
        )
    else:
        conn.execute(
            f"""
            INSERT INTO commercial_purchase_events ({", ".join(cols)}, evidence_json, created_at, updated_at)
            VALUES ({", ".join("?" * len(cols))}, ?, ?, ?)
            """,
            (*values, evidence_json, now, now),
        )
        event_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    for item in plan.line_items:
        conn.execute(
            """
            INSERT INTO commercial_purchase_event_items (
              purchase_event_id, line_number, ref_code, product_name, brand,
              quantity, net_amount_clp, evidence_source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                item["line_number"],
                item.get("ref_code"),
                item["product_name"],
                item.get("brand"),
                item.get("quantity"),
                item.get("net_amount_clp"),
                item.get("evidence_source"),
                now,
            ),
        )

    for att in plan.attachments:
        conn.execute(
            """
            INSERT INTO commercial_purchase_event_attachments (
              purchase_event_id, source_attachment_id, filename, mime_type,
              document_type, extracted_text_present, extracted_amounts_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                att.id,
                att.filename,
                att.content_type,
                _attachment_document_type(att.filename),
                0,
                None,
                now,
            ),
        )

    conn.commit()
    return event_id


def plan_to_report_dict(plan: PromotionPlan) -> dict[str, Any]:
    contact_email = plan.event_fields.get("buyer_contact_email")
    return {
        "action": plan.action,
        "existing_event_id": plan.existing_event_id,
        "email": {
            "id": plan.email.id,
            "subject": plan.email.subject,
            "sender": plan.email.sender,
            "date_iso": plan.email.date_iso,
            "source_file": plan.email.source_file,
            "message_id": plan.email.message_id,
        },
        "attachments": [
            {"id": a.id, "filename": a.filename, "content_type": a.content_type}
            for a in plan.attachments
        ],
        "event": plan.event_fields,
        "line_items": plan.line_items,
        "buyer_domain_resolved": domain_of(contact_email if isinstance(contact_email, str) else None),
    }


def connect_sqlite_rw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path.resolve()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
