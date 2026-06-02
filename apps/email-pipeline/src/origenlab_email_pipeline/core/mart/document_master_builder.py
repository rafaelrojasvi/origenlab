"""Rebuild ``document_master`` and compute per-email document aggregates."""

from __future__ import annotations

import sqlite3
import time

from origenlab_email_pipeline.business_mart import (
    DocAgg,
    clean_document_preview,
    doc_aggregates,
    domain_of,
    emails_in,
    equipment_tags_from_text,
    primary_sender_email,
)
from origenlab_email_pipeline.freshness_dates import email_date_iso_for_mart_timeline
from origenlab_email_pipeline.pipeline_run_recorder import get_kv, set_kv
from origenlab_email_pipeline.progress import iter_with_progress

DOC_SIGNATURE_KV = "mart_document_master_signature_v1"


def attachment_extension(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    if "." not in s:
        return ""
    return s.rsplit(".", 1)[-1][:12]


def document_signature(conn: sqlite3.Connection) -> str:
    a = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM attachments").fetchone()
    ae = conn.execute("SELECT COUNT(*), COALESCE(MAX(attachment_id), 0) FROM attachment_extracts").fetchone()
    a_count, a_max = int(a[0] if a else 0), int(a[1] if a else 0)
    ae_count, ae_max = int(ae[0] if ae else 0), int(ae[1] if ae else 0)
    return f"{a_count}:{a_max}:{ae_count}:{ae_max}"


def rebuild_document_master(
    conn: sqlite3.Connection,
    *,
    internal_domains: set[str],
    mart_slack: int,
    skip_if_unchanged: bool,
) -> DocAgg:
    """Rebuild ``document_master`` when needed; return doc aggregates for email scan."""
    stage_t0 = time.monotonic()
    skip_document_master = False
    if skip_if_unchanged:
        sig = document_signature(conn)
        last_sig = get_kv(conn, DOC_SIGNATURE_KV) or ""
        if sig == last_sig:
            skip_document_master = True
            print("document_master unchanged signature; skipping rebuild.")
        else:
            set_kv(conn, DOC_SIGNATURE_KV, sig)

    inserted_docs = 0
    if not skip_document_master:
        doc_rows = conn.execute(
            """
            SELECT
              a.id AS attachment_id,
              a.email_id,
              a.filename,
              a.content_type,
              e.sender,
              e.recipients,
              e.date_iso,
              e.subject,
              e.top_reply_clean,
              ae.detected_doc_type,
              ae.text_preview,
              ae.has_quote_terms,
              ae.has_invoice_terms,
              ae.has_purchase_terms,
              ae.has_price_list_terms
            FROM attachment_extracts ae
            JOIN attachments a ON a.id = ae.attachment_id
            JOIN emails e ON e.id = a.email_id
            WHERE ae.extract_status='success'
            """
        ).fetchall()

        for r in iter_with_progress(doc_rows, desc="document_master"):
            attachment_id = int(r[0])
            email_id = int(r[1])
            filename = r[2] or ""
            sender_email = primary_sender_email(r[4] or "") or ""
            sender_domain = domain_of(sender_email) or ""
            recip_domains = [domain_of(x) for x in emails_in(r[5] or "")]
            recip_domains = [d for d in recip_domains if d]
            recipient_domain = ""
            for d in recip_domains:
                if d not in internal_domains:
                    recipient_domain = d
                    break
            if not recipient_domain and recip_domains:
                recipient_domain = recip_domains[0]

            subj = r[7] or ""
            top = r[8] or ""
            preview_raw = (r[10] or "")[:2000]
            preview_clean, preview_q = clean_document_preview(preview_raw)
            tags = equipment_tags_from_text(subj + "\n" + top + "\n" + preview_clean)
            conn.execute(
                """
                INSERT OR REPLACE INTO document_master
                (attachment_id, email_id, filename, extension, sender_email, sender_domain,
                 recipient_domain, sent_at, doc_type, extracted_preview_raw, extracted_preview_clean, preview_quality_score,
                 has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms,
                 equipment_tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    email_id,
                    filename,
                    attachment_extension(filename),
                    sender_email,
                    sender_domain,
                    recipient_domain,
                    email_date_iso_for_mart_timeline(r[6], slack_days=mart_slack),
                    (r[9] or "unknown"),
                    preview_raw,
                    preview_clean,
                    float(preview_q),
                    int(r[11] or 0),
                    int(r[12] or 0),
                    int(r[13] or 0),
                    int(r[14] or 0),
                    ",".join(tags),
                ),
            )
            inserted_docs += 1
        conn.commit()
        print(f"document_master rows: {inserted_docs:,}")
    print(f"[timing] document_master_seconds={time.monotonic() - stage_t0:.2f}")

    return doc_aggregates(
        conn.execute(
            """
            SELECT a.email_id, ae.detected_doc_type,
                   COALESCE(ae.has_quote_terms,0),
                   COALESCE(ae.has_invoice_terms,0),
                   COALESCE(ae.has_purchase_terms,0),
                   COALESCE(ae.has_price_list_terms,0)
            FROM attachment_extracts ae
            JOIN attachments a ON a.id = ae.attachment_id
            WHERE ae.extract_status='success'
            """
        )
    )
