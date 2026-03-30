#!/usr/bin/env python3
"""Phase 2.4 validation: attachment_extracts coverage, counts, and samples."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect, init_schema


def _q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _print_kv(k: str, v) -> None:
    print(f"{k}|{v}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=8, help="samples per section")
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()

    conn = connect(db_path)
    init_schema(conn)

    print("=== Phase 2.4 validation ===")
    print()
    print(f"DB: {db_path}")
    print()

    total_emails = _q(conn, "SELECT COUNT(*) FROM emails")
    total_atts = _q(conn, "SELECT COUNT(*) FROM attachments")
    total_extracts = _q(conn, "SELECT COUNT(*) FROM attachment_extracts")

    print("--- Totals ---")
    print(f"emails: {total_emails:,}")
    print(f"attachments: {total_atts:,}")
    print(f"attachment_extracts: {total_extracts:,}")
    print()

    print("--- Extracts by status ---")
    for status, c in conn.execute(
        "SELECT extract_status, COUNT(*) FROM attachment_extracts GROUP BY extract_status ORDER BY COUNT(*) DESC"
    ):
        print(f"  {status!r}: {c:,}")
    print()

    print("--- Extracts by method ---")
    for method, c in conn.execute(
        "SELECT extract_method, COUNT(*) FROM attachment_extracts GROUP BY extract_method ORDER BY COUNT(*) DESC"
    ):
        print(f"  {method!r}: {c:,}")
    print()

    print("--- Detected doc types (success only) ---")
    for dt, c in conn.execute(
        """
        SELECT detected_doc_type, COUNT(*)
        FROM attachment_extracts
        WHERE extract_status='success'
        GROUP BY detected_doc_type
        ORDER BY COUNT(*) DESC
        """
    ):
        print(f"  {dt!r}: {c:,}")
    print()

    print("--- Signal counts (success only) ---")
    for name in ("has_quote_terms", "has_invoice_terms", "has_price_list_terms", "has_purchase_terms"):
        c = _q(
            conn,
            f"""
            SELECT COUNT(*)
            FROM attachment_extracts
            WHERE extract_status='success' AND {name}=1
            """,
        )
        print(f"  {name}: {c:,}")
    print()

    print("--- Top error messages (failed/skipped) ---")
    for msg, c in conn.execute(
        """
        SELECT COALESCE(error_message,''), COUNT(*)
        FROM attachment_extracts
        WHERE extract_status IN ('failed','skipped')
        GROUP BY COALESCE(error_message,'')
        ORDER BY COUNT(*) DESC
        LIMIT 10
        """
    ):
        msg = (msg or "").replace("\n", " ")[:140]
        print(f"  {c:,}x  {msg!r}")
    print()

    def sample(where_sql: str, title: str) -> None:
        print(f"--- Sample: {title} ---")
        rows = conn.execute(
            f"""
            SELECT ae.attachment_id, ae.extract_method, ae.detected_doc_type,
                   a.filename, a.content_type, a.size_bytes,
                   SUBSTR(ae.text_preview, 1, 220) AS prev
            FROM attachment_extracts ae
            JOIN attachments a ON a.id = ae.attachment_id
            WHERE {where_sql}
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (args.samples,),
        ).fetchall()
        for r in rows:
            prev = (r[6] or "").replace("\n", " ")
            print(
                f"  att_id={r[0]} method={r[1]} doc_type={r[2]} size={r[5]} "
                f"ctype={r[4]!r} filename={r[3]!r} preview={prev!r}"
            )
        print()

    sample("ae.extract_status='success' AND ae.extract_method='pdf_text'", "success pdf_text")
    sample("ae.extract_status='success' AND ae.extract_method='docx'", "success docx")
    sample("ae.extract_status='success' AND ae.extract_method='xlsx'", "success xlsx")
    sample("ae.extract_status='success' AND ae.extract_method='csv'", "success csv")
    sample("ae.extract_status='success' AND ae.extract_method='xml'", "success xml")
    sample("ae.extract_status='empty'", "empty extracts (likely scanned PDFs or blank docs)")

    # Quick join to email subjects for business safety spot-checks.
    sample(
        "ae.extract_status='success' AND ae.detected_doc_type IN ('quote','invoice','purchase_order','price_list')",
        "classified business docs",
    )

    print("Done.")
    print()
    # machine-readable tail (stable keys)
    _print_kv("emails_total", total_emails)
    _print_kv("attachments_total", total_atts)
    _print_kv("extracts_total", total_extracts)
    _print_kv("extracts_success", _q(conn, "SELECT COUNT(*) FROM attachment_extracts WHERE extract_status='success'"))
    _print_kv("extracts_failed", _q(conn, "SELECT COUNT(*) FROM attachment_extracts WHERE extract_status='failed'"))
    _print_kv("extracts_skipped", _q(conn, "SELECT COUNT(*) FROM attachment_extracts WHERE extract_status='skipped'"))
    _print_kv("extracts_empty", _q(conn, "SELECT COUNT(*) FROM attachment_extracts WHERE extract_status='empty'"))
    conn.close()


if __name__ == "__main__":
    main()

