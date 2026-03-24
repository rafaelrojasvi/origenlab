"""SQLite metrics and queries for the client email report (no HTML).

Keeps heavy SQL and read-only attachment/extract passes importable and testable.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from origenlab_email_pipeline.attachment_report_sql import (
    attachment_business_doc_filename_extension_expr_sql,
    attachment_business_doc_predicate_sql,
    attachment_delivery_noise_predicate_sql,
)


def merged_aggregate_sql() -> str:
    """Single full-table scan: classification + cotización∧equipo (saves one disk pass)."""
    blob = "LOWER(COALESCE(subject,'') || ' ' || COALESCE(body,''))"
    send = "LOWER(COALESCE(sender,''))"
    subj = "LOWER(COALESCE(subject,''))"
    return f"""
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN date_iso IS NOT NULL AND length(trim(date_iso)) >= 4 THEN 1 ELSE 0 END) AS with_date,
          SUM(CASE WHEN length(trim(coalesce(body,''))) > 0 THEN 1 ELSE 0 END) AS with_body,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' THEN 1 ELSE 0 END) AS cotizacion,
          SUM(CASE WHEN {blob} LIKE '%proveedor%' THEN 1 ELSE 0 END) AS proveedor,
          SUM(CASE WHEN {blob} LIKE '%factura%' OR {blob} LIKE '%invoice%' THEN 1 ELSE 0 END) AS factura_invoice,
          SUM(CASE WHEN {blob} LIKE '%pedido%' OR {blob} LIKE '%purchase order%'
                    OR {subj} LIKE '%orden de compra%' OR {subj} LIKE '%oc %' THEN 1 ELSE 0 END) AS pedido_oc,
          SUM(CASE WHEN {blob} LIKE '%universidad%'
                    OR {blob} LIKE '%uchile%' OR {blob} LIKE '%uc.cl%' OR {blob} LIKE '%puc.cl%'
                    OR {blob} LIKE '%utfsm%' OR {blob} LIKE '%udec%' OR {blob} LIKE '%usach%'
                    OR {blob} LIKE '%unab%' OR {blob} LIKE '%ucn.cl%' OR {blob} LIKE '%uach%'
                    OR {blob} LIKE '%.edu.%' THEN 1 ELSE 0 END) AS universidad,
          SUM(CASE WHEN {send} LIKE '%mailer-daemon%' OR {send} LIKE '%postmaster%'
                    OR {subj} LIKE '%delivery status%' OR {subj} LIKE '%undeliverable%'
                    OR {subj} LIKE '%mail delivery failed%'
                    OR {blob} LIKE '%notificación de estado de entrega%'
                    OR {blob} LIKE '%returning message to sender%' THEN 1 ELSE 0 END) AS bounce_like,
          SUM(CASE WHEN {blob} LIKE '%microscop%' THEN 1 ELSE 0 END) AS eq_microscopio,
          SUM(CASE WHEN {blob} LIKE '%centrifug%' THEN 1 ELSE 0 END) AS eq_centrifuga,
          SUM(CASE WHEN {blob} LIKE '%espectrofotomet%' OR {blob} LIKE '%spectrophotomet%' THEN 1 ELSE 0 END) AS eq_espectrofotometro,
          SUM(CASE WHEN {blob} LIKE '%phmetro%' OR {blob} LIKE '% ph meter%' THEN 1 ELSE 0 END) AS eq_phmetro,
          SUM(CASE WHEN {blob} LIKE '%autoclave%' THEN 1 ELSE 0 END) AS eq_autoclave,
          SUM(CASE WHEN {blob} LIKE '%balanza%' OR {blob} LIKE '%balance analit%' THEN 1 ELSE 0 END) AS eq_balanza,
          SUM(CASE WHEN {blob} LIKE '%cromatograf%' OR {blob} LIKE '%hplc%' OR {blob} LIKE '%gc-ms%' THEN 1 ELSE 0 END) AS eq_cromatografia,
          SUM(CASE WHEN {blob} LIKE '%incubador%' OR {blob} LIKE '%incubator%' THEN 1 ELSE 0 END) AS eq_incubadora,
          SUM(CASE WHEN {blob} LIKE '%titulador%' OR {blob} LIKE '%titrator%' THEN 1 ELSE 0 END) AS eq_titulador,
          SUM(CASE WHEN {blob} LIKE '%liofiliz%' OR {blob} LIKE '%lyophil%' THEN 1 ELSE 0 END) AS eq_liofilizador,
          SUM(CASE WHEN {blob} LIKE '%mufla%' OR {blob} LIKE '%horno%' THEN 1 ELSE 0 END) AS eq_horno_mufla,
          SUM(CASE WHEN {blob} LIKE '%pipet%' OR {blob} LIKE '%pipeta%' THEN 1 ELSE 0 END) AS eq_pipetas,
          SUM(CASE WHEN {blob} LIKE '%medidor de humedad%' OR {blob} LIKE '%grain moisture%' THEN 1 ELSE 0 END) AS eq_humedad_granos,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%microscop%' THEN 1 ELSE 0 END) AS cotiz_microscopio,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%centrifug%' THEN 1 ELSE 0 END) AS cotiz_centrifuga,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%balanza%' THEN 1 ELSE 0 END) AS cotiz_balanza,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND ({blob} LIKE '%cromatograf%' OR {blob} LIKE '%hplc%') THEN 1 ELSE 0 END) AS cotiz_cromatografia,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%autoclave%' THEN 1 ELSE 0 END) AS cotiz_autoclave,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%phmetro%' THEN 1 ELSE 0 END) AS cotiz_phmetro,
          SUM(CASE WHEN {blob} LIKE '%cotiz%' AND {blob} LIKE '%medidor de humedad%' THEN 1 ELSE 0 END) AS cotiz_humedad_granos
        FROM emails
        """


_MERGED_AGG_NAMES = [
    "total",
    "with_date",
    "with_body",
    "cotizacion",
    "proveedor",
    "factura_invoice",
    "pedido_oc",
    "universidad",
    "bounce_like",
    "eq_microscopio",
    "eq_centrifuga",
    "eq_espectrofotometro",
    "eq_phmetro",
    "eq_autoclave",
    "eq_balanza",
    "eq_cromatografia",
    "eq_incubadora",
    "eq_titulador",
    "eq_liofilizador",
    "eq_horno_mufla",
    "eq_pipetas",
    "eq_humedad_granos",
    "cotiz_microscopio",
    "cotiz_centrifuga",
    "cotiz_balanza",
    "cotiz_cromatografia",
    "cotiz_autoclave",
    "cotiz_phmetro",
    "cotiz_humedad_granos",
]


def run_merged_aggregate(conn: sqlite3.Connection) -> dict:
    row = conn.execute(merged_aggregate_sql()).fetchone()
    return dict(zip(_MERGED_AGG_NAMES, row))


def run_year_cotiz_only(conn: sqlite3.Connection) -> list[dict]:
    blob = "LOWER(COALESCE(subject,'') || ' ' || COALESCE(body,''))"
    years = conn.execute(
        f"""
        SELECT substr(date_iso, 1, 4) AS y, COUNT(*) AS c
        FROM emails
        WHERE date_iso IS NOT NULL AND length(trim(date_iso)) >= 4
          AND substr(date_iso, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
          AND {blob} LIKE '%cotiz%'
        GROUP BY y
        ORDER BY y
        """
    ).fetchall()
    return [{"year": r[0], "count": r[1]} for r in years]


def run_year_counts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT substr(date_iso, 1, 4) AS y, COUNT(*) AS c
        FROM emails
        WHERE date_iso IS NOT NULL AND length(trim(date_iso)) >= 4
          AND substr(date_iso, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        GROUP BY y
        ORDER BY y
        """
    ).fetchall()
    return [{"year": r[0], "count": r[1]} for r in rows]


def run_attachment_metrics(db_path: Path) -> dict | None:
    """Phase 2.3: refined attachment metrics (business-doc, non-inline).

    Uses a dedicated read-only SQLite connection to avoid cross-thread/process
    interactions in the main report generator.

    Returns None if:
    - the attachments table doesn't exist, or
    - queries fail (prints a short warning to stderr).
    """
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='attachments'"
        ).fetchone()
        if not has_table:
            conn.close()
            return None
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        print(f"[warn] attachments metrics unavailable: {e}", file=sys.stderr)
        return None

    _noise = attachment_delivery_noise_predicate_sql("a")
    _business_doc = attachment_business_doc_predicate_sql("a")
    ext_expr = attachment_business_doc_filename_extension_expr_sql("a")

    try:
        emails_with_attachments = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE has_attachments = 1"
        ).fetchone()[0]
        emails_non_inline = conn.execute(
            """
            SELECT COUNT(DISTINCT a.email_id) FROM attachments a
            INNER JOIN emails e ON e.id = a.email_id
            WHERE COALESCE(a.is_inline, 0) = 0
            """
        ).fetchone()[0]
        emails_business_doc = conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.email_id) FROM attachments a
            INNER JOIN emails e ON e.id = a.email_id
            WHERE {_business_doc}
            """
        ).fetchone()[0]

        class_images = conn.execute(
            "SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id WHERE LOWER(COALESCE(a.content_type,'')) LIKE 'image/%'"
        ).fetchone()[0]
        class_pdf = conn.execute(
            "SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id WHERE LOWER(COALESCE(a.content_type,'')) LIKE 'application/pdf%' OR LOWER(COALESCE(a.filename,'')) LIKE '%.pdf'"
        ).fetchone()[0]
        class_excel = conn.execute(
            """
            SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
            WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.xls' OR LOWER(COALESCE(a.filename,'')) GLOB '*.xlsx' OR LOWER(COALESCE(a.filename,'')) GLOB '*.csv'
               OR LOWER(COALESCE(a.content_type,'')) LIKE '%spreadsheet%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%ms-excel%'
            """
        ).fetchone()[0]
        class_word = conn.execute(
            """
            SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
            WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.doc' OR LOWER(COALESCE(a.filename,'')) GLOB '*.docx'
               OR LOWER(COALESCE(a.content_type,'')) LIKE '%msword%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%wordprocessing%'
            """
        ).fetchone()[0]
        class_archives = conn.execute(
            """
            SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
            WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.zip' OR LOWER(COALESCE(a.filename,'')) GLOB '*.rar'
               OR LOWER(COALESCE(a.content_type,'')) LIKE '%zip%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%x-zip%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%rar%'
            """
        ).fetchone()[0]
        class_noise = conn.execute(
            f"SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id WHERE {_noise}"
        ).fetchone()[0]
        class_other = conn.execute(
            f"""
            SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
            WHERE LOWER(COALESCE(a.content_type,'')) NOT LIKE 'image/%'
              AND LOWER(COALESCE(a.content_type,'')) NOT LIKE 'application/pdf%' AND LOWER(COALESCE(a.filename,'')) NOT LIKE '%.pdf'
              AND NOT (LOWER(COALESCE(a.filename,'')) GLOB '*.xls' OR LOWER(COALESCE(a.filename,'')) GLOB '*.xlsx' OR LOWER(COALESCE(a.filename,'')) GLOB '*.csv'
                   OR LOWER(COALESCE(a.content_type,'')) LIKE '%spreadsheet%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%ms-excel%')
              AND NOT (LOWER(COALESCE(a.filename,'')) GLOB '*.doc' OR LOWER(COALESCE(a.filename,'')) GLOB '*.docx'
                   OR LOWER(COALESCE(a.content_type,'')) LIKE '%msword%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%wordprocessing%')
              AND NOT (LOWER(COALESCE(a.filename,'')) GLOB '*.zip' OR LOWER(COALESCE(a.content_type,'')) LIKE '%zip%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%x-zip%')
              AND NOT ({_noise})
            """
        ).fetchone()[0]

        top_business_ext = conn.execute(
            f"""
            SELECT {ext_expr} AS ext, COUNT(*) AS c
            FROM attachments a INNER JOIN emails e ON e.id = a.email_id
            WHERE {_business_doc} AND a.filename IS NOT NULL AND instr(a.filename, '.') > 0
            GROUP BY ext ORDER BY c DESC LIMIT 10
            """
        ).fetchall()

        cotizacion_business_doc = conn.execute(
            f"""
            SELECT COUNT(DISTINCT e.id) FROM emails e
            INNER JOIN attachments a ON a.email_id = e.id AND {_business_doc}
            WHERE (e.subject LIKE '%cotización%' OR e.subject LIKE '%cotizacion%' OR e.subject LIKE '%Cotización%' OR e.subject LIKE '%Cotizacion%'
                   OR e.top_reply_clean LIKE '%cotización%' OR e.top_reply_clean LIKE '%cotizacion%')
            """
        ).fetchone()[0]

        out = {
            "emails_with_attachments": emails_with_attachments,
            "emails_with_non_inline_attachments": emails_non_inline,
            "emails_with_business_doc_attachments": emails_business_doc,
            "attachment_counts_by_broad_class": {
                "images": class_images,
                "pdf": class_pdf,
                "excel_csv": class_excel,
                "word": class_word,
                "archives": class_archives,
                "delivery_report_noise": class_noise,
                "other_docs": class_other,
            },
            "top_business_doc_extensions": [{"ext": r[0], "count": r[1]} for r in top_business_ext],
            "cotizacion_emails_with_business_doc_attachments": cotizacion_business_doc,
        }
        conn.close()
        return out
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        print(f"[warn] attachments metrics query failed: {e}", file=sys.stderr)
        return None


def run_attachment_extract_metrics(db_path: Path) -> dict | None:
    """Phase 2.4: compact metrics for attachment_extracts."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='attachment_extracts'"
        ).fetchone()
        if not has_table:
            conn.close()
            return None
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        print(f"[warn] attachment_extracts metrics unavailable: {e}", file=sys.stderr)
        return None

    try:
        total = int(conn.execute("SELECT COUNT(*) AS c FROM attachment_extracts").fetchone()["c"])
        by_status = {
            r["extract_status"]: int(r["c"])
            for r in conn.execute(
                "SELECT extract_status, COUNT(*) AS c FROM attachment_extracts GROUP BY extract_status"
            ).fetchall()
        }
        by_method = {
            r["extract_method"]: int(r["c"])
            for r in conn.execute(
                "SELECT extract_method, COUNT(*) AS c FROM attachment_extracts GROUP BY extract_method"
            ).fetchall()
        }
        by_doc_type = {
            (r["detected_doc_type"] or "unknown"): int(r["c"])
            for r in conn.execute(
                """
                SELECT detected_doc_type, COUNT(*) AS c
                FROM attachment_extracts
                WHERE extract_status='success'
                GROUP BY detected_doc_type
                ORDER BY c DESC
                """
            ).fetchall()
        }
        signal_counts = {
            "has_quote_terms": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM attachment_extracts WHERE extract_status='success' AND has_quote_terms=1"
                ).fetchone()["c"]
            ),
            "has_invoice_terms": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM attachment_extracts WHERE extract_status='success' AND has_invoice_terms=1"
                ).fetchone()["c"]
            ),
            "has_price_list_terms": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM attachment_extracts WHERE extract_status='success' AND has_price_list_terms=1"
                ).fetchone()["c"]
            ),
            "has_purchase_terms": int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM attachment_extracts WHERE extract_status='success' AND has_purchase_terms=1"
                ).fetchone()["c"]
            ),
        }
        top_doc_types = sorted(by_doc_type.items(), key=lambda x: x[1], reverse=True)[:8]
        return {
            "extracts_total": total,
            "by_status": by_status,
            "by_method": by_method,
            "by_doc_type_success": by_doc_type,
            "signal_counts_success": signal_counts,
            "top_doc_types_success": [{"doc_type": k, "count": v} for k, v in top_doc_types],
        }
    except Exception as e:
        print(f"[warn] attachment_extracts query failed: {e}", file=sys.stderr)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
