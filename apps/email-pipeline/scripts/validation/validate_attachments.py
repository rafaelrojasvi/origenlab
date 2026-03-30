#!/usr/bin/env python3
"""Validate attachment metadata (Phase 2.3) on the SQLite DB."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.attachment_report_sql import (
    attachment_business_doc_filename_extension_expr_sql,
    attachment_business_doc_predicate_sql,
    attachment_delivery_noise_predicate_sql,
)
from origenlab_email_pipeline.config import load_settings


def main() -> None:
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== Attachments validation (Phase 2.3) ===")
    print("DB:", db_path, "\n")

    # --- Audit: how each metric is computed ---
    # total_emails       = COUNT(*) FROM emails
    # total_attachments  = COUNT(*) FROM attachments
    # emails_with_attachments = COUNT(*) FROM emails WHERE has_attachments = 1
    #   (must be <= total_emails; do NOT use COUNT(DISTINCT email_id) FROM attachments,
    #    which can exceed total_emails after dedupe due to orphan attachment rows)

    total_emails = cur.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    total_attachments = cur.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    emails_with_attachments = cur.execute(
        "SELECT COUNT(*) FROM emails WHERE has_attachments = 1"
    ).fetchone()[0]

    print("--- Metric audit ---")
    print("  total_emails:            COUNT(*) FROM emails")
    print("  total_attachments:        COUNT(*) FROM attachments")
    print("  emails_with_attachments:  COUNT(*) FROM emails WHERE has_attachments = 1")
    print()
    print(f"Total emails: {total_emails:,}")
    print(f"Total attachments: {total_attachments:,}")
    print(f"Emails with attachments: {emails_with_attachments:,}")

    # Side-by-side diagnostics (detect orphan attachments and dedupe skew)
    count_emails = cur.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    count_att = cur.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    distinct_email_id_att = cur.execute(
        "SELECT COUNT(DISTINCT email_id) FROM attachments"
    ).fetchone()[0]
    emails_has_att = cur.execute(
        "SELECT COUNT(*) FROM emails WHERE has_attachments = 1"
    ).fetchone()[0]
    sum_attachment_count = cur.execute(
        "SELECT SUM(attachment_count) FROM emails"
    ).fetchone()[0]
    # Attachments whose email_id exists in emails
    att_with_email = cur.execute(
        "SELECT COUNT(*) FROM attachments a WHERE EXISTS (SELECT 1 FROM emails e WHERE e.id = a.email_id)"
    ).fetchone()[0]
    orphan_att = cur.execute(
        "SELECT COUNT(*) FROM attachments a WHERE NOT EXISTS (SELECT 1 FROM emails e WHERE e.id = a.email_id)"
    ).fetchone()[0]

    print("\n--- Side-by-side counts ---")
    print(f"  COUNT(*) FROM emails:                      {count_emails:,}")
    print(f"  COUNT(*) FROM attachments:                {count_att:,}")
    print(f"  COUNT(DISTINCT email_id) FROM attachments: {distinct_email_id_att:,}")
    print(f"  COUNT(*) FROM emails WHERE has_attachments=1: {emails_has_att:,}")
    print(f"  SUM(attachment_count) FROM emails:         {sum_attachment_count:,}")
    print(f"  Attachment rows with existing email_id:   {att_with_email:,}")
    print(f"  Orphan attachment rows (email_id not in emails): {orphan_att:,}")

    # --- Attachment reporting refinement (broad classes, business-doc) ---
    # Business-doc / noise SQL shared with client_report_metrics (alias `a` in joins)
    _noise = attachment_delivery_noise_predicate_sql("a")
    _business_doc = attachment_business_doc_predicate_sql("a")
    emails_non_inline = cur.execute(
        """
        SELECT COUNT(DISTINCT a.email_id) FROM attachments a
        INNER JOIN emails e ON e.id = a.email_id
        WHERE COALESCE(a.is_inline, 0) = 0
        """
    ).fetchone()[0]
    emails_business_doc = cur.execute(
        f"""
        SELECT COUNT(DISTINCT a.email_id) FROM attachments a
        INNER JOIN emails e ON e.id = a.email_id
        WHERE {_business_doc}
        """
    ).fetchone()[0]
    print("\n--- Attachment reporting refinement ---")
    print(f"  Total emails with attachments:        {emails_with_attachments:,}")
    print(f"  Emails with non-inline attachments:  {emails_non_inline:,}")
    print(f"  Emails with business-doc attachments: {emails_business_doc:,}")

    # Counts by broad class (attachments only; each row in one class)
    class_images = cur.execute(
        "SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id WHERE LOWER(COALESCE(a.content_type,'')) LIKE 'image/%'"
    ).fetchone()[0]
    class_pdf = cur.execute(
        "SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id WHERE LOWER(COALESCE(a.content_type,'')) LIKE 'application/pdf%' OR LOWER(COALESCE(a.filename,'')) LIKE '%.pdf'"
    ).fetchone()[0]
    class_excel = cur.execute(
        """
        SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
        WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.xls' OR LOWER(COALESCE(a.filename,'')) GLOB '*.xlsx' OR LOWER(COALESCE(a.filename,'')) GLOB '*.csv'
           OR LOWER(COALESCE(a.content_type,'')) LIKE '%spreadsheet%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%ms-excel%'
        """
    ).fetchone()[0]
    class_word = cur.execute(
        """
        SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
        WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.doc' OR LOWER(COALESCE(a.filename,'')) GLOB '*.docx'
           OR LOWER(COALESCE(a.content_type,'')) LIKE '%msword%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%wordprocessing%'
        """
    ).fetchone()[0]
    class_archives = cur.execute(
        """
        SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
        WHERE LOWER(COALESCE(a.filename,'')) GLOB '*.zip' OR LOWER(COALESCE(a.filename,'')) GLOB '*.rar'
           OR LOWER(COALESCE(a.content_type,'')) LIKE '%zip%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%x-zip%' OR LOWER(COALESCE(a.content_type,'')) LIKE '%rar%'
        """
    ).fetchone()[0]
    class_noise = cur.execute(
        f"""
        SELECT COUNT(*) FROM attachments a INNER JOIN emails e ON e.id = a.email_id
        WHERE {_noise}
        """
    ).fetchone()[0]
    class_other = cur.execute(
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
    print("  Attachment counts by broad class (existing emails only):")
    print(f"    images:              {class_images:,}")
    print(f"    pdf:                 {class_pdf:,}")
    print(f"    excel/csv:           {class_excel:,}")
    print(f"    word:                {class_word:,}")
    print(f"    archives:            {class_archives:,}")
    print(f"    delivery/report:     {class_noise:,}")
    print(f"    other docs:          {class_other:,}")

    # Top business-doc extensions (existing emails only)
    ext_expr_main = attachment_business_doc_filename_extension_expr_sql("a")
    print("  Top business-doc extensions (top 10):")
    for row in cur.execute(
        f"""
        SELECT {ext_expr_main} AS ext, COUNT(*) AS c
        FROM attachments a INNER JOIN emails e ON e.id = a.email_id
        WHERE {_business_doc} AND a.filename IS NOT NULL AND instr(a.filename, '.') > 0
        GROUP BY ext ORDER BY c DESC LIMIT 10
        """
    ):
        print(f"    .{row[0]}: {row[1]:,}")

    # Cotización emails with business-doc attachments (subject or top_reply_clean contains cotización/cotizacion)
    cotiz_business = cur.execute(
        f"""
        SELECT COUNT(DISTINCT e.id) FROM emails e
        INNER JOIN attachments a ON a.email_id = e.id AND {_business_doc}
        WHERE (e.subject LIKE '%cotización%' OR e.subject LIKE '%cotizacion%' OR e.subject LIKE '%Cotización%' OR e.subject LIKE '%Cotizacion%'
               OR e.top_reply_clean LIKE '%cotización%' OR e.top_reply_clean LIKE '%cotizacion%')
        """
    ).fetchone()[0]
    print(f"  Cotización emails with business-doc attachments: {cotiz_business:,}")

    print("\n--- By content_type (top 15) ---")
    for row in cur.execute(
        """
        SELECT COALESCE(content_type,'(none)') AS ct, COUNT(*) AS c
        FROM attachments
        GROUP BY ct
        ORDER BY c DESC
        LIMIT 15
        """
    ):
        print(f"  {row['ct']!r}: {row['c']:,}")

    print("\n--- By extension (top 15) ---")
    # Extension = substring after last dot. SQLite has no REVERSE; use nested after-first-dot.
    # e1 = after first dot; if e1 has no dot then ext=e1, else ext = after first dot of e1, etc.
    for row in cur.execute(
        """
        SELECT LOWER(
            CASE
                WHEN instr(substr(filename, instr(filename, '.') + 1), '.') = 0
                THEN substr(filename, instr(filename, '.') + 1)
                WHEN instr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), '.') = 0
                THEN substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1)
                ELSE substr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), instr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), '.') + 1)
            END
        ) AS ext,
               COUNT(*) AS c
        FROM attachments
        WHERE filename IS NOT NULL AND instr(filename, '.') > 0
        GROUP BY ext
        ORDER BY c DESC
        LIMIT 15
        """
    ):
        print(f"  .{row['ext']}: {row['c']:,}")

    print("\n--- Inline vs non-inline ---")
    for row in cur.execute(
        """
        SELECT COALESCE(is_inline, 0) AS inline_flag, COUNT(*) AS c
        FROM attachments
        GROUP BY inline_flag
        ORDER BY inline_flag
        """
    ):
        label = "inline" if row["inline_flag"] == 1 else "attachment"
        print(f"  {label}: {row['c']:,}")

    print("\n--- Type-specific email counts ---")
    def count_emails_with_ext(conds: str) -> int:
        q = f"""
        SELECT COUNT(DISTINCT email_id)
        FROM attachments
        WHERE {conds}
        """
        return cur.execute(q).fetchone()[0]

    pdf_emails = count_emails_with_ext(
        "LOWER(content_type) LIKE 'application/pdf%' OR LOWER(filename) LIKE '%.pdf'"
    )
    excel_emails = count_emails_with_ext(
        "LOWER(filename) GLOB '*.xls' OR LOWER(filename) GLOB '*.xlsx' OR LOWER(filename) GLOB '*.csv'"
    )
    word_emails = count_emails_with_ext(
        "LOWER(filename) GLOB '*.doc' OR LOWER(filename) GLOB '*.docx'"
    )
    image_emails = count_emails_with_ext("LOWER(content_type) LIKE 'image/%'")

    print(f"  Emails with PDF: {pdf_emails:,}")
    print(f"  Emails with Excel (xls/xlsx/csv): {excel_emails:,}")
    print(f"  Emails with Word (doc/docx): {word_emails:,}")
    print(f"  Emails with images: {image_emails:,}")

    print("\n--- Consistency checks (emails vs attachments) ---")
    drift_has = cur.execute(
        """
        SELECT COUNT(*) FROM emails e
        LEFT JOIN (
          SELECT email_id, COUNT(*) AS c FROM attachments GROUP BY email_id
        ) a ON e.id = a.email_id
        WHERE COALESCE(e.has_attachments,0) = 1 AND COALESCE(a.c,0) = 0
        """
    ).fetchone()[0]
    drift_count = cur.execute(
        """
        SELECT COUNT(*) FROM emails e
        LEFT JOIN (
          SELECT email_id, COUNT(*) AS c FROM attachments GROUP BY email_id
        ) a ON e.id = a.email_id
        WHERE COALESCE(e.attachment_count,0) != COALESCE(a.c,0)
        """
    ).fetchone()[0]
    print(f"  has_attachments=1 but no attachment rows: {drift_has:,}")
    print(f"  attachment_count != actual row count: {drift_count:,}")

    print("\n--- Diagnostics ---")
    missing_name = cur.execute(
        """
        SELECT COUNT(*) FROM attachments
        WHERE filename IS NULL AND size_bytes > 0
        """
    ).fetchone()[0]
    zero_size = cur.execute(
        "SELECT COUNT(*) FROM attachments WHERE size_bytes = 0"
    ).fetchone()[0]
    duplicate_hash = cur.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT sha256 FROM attachments
          WHERE sha256 IS NOT NULL
          GROUP BY sha256
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    print(f"  Attachments with no filename but size > 0: {missing_name:,}")
    print(f"  Attachments with size_bytes = 0: {zero_size:,}")
    print(f"  Distinct sha256 values with duplicates: {duplicate_hash:,}")

    # Zero-byte attachments: breakdown and business-doc count
    print("\n--- Zero-byte attachments (size_bytes = 0) ---")
    zero_by_content = cur.execute(
        """
        SELECT COALESCE(content_type, '(none)') AS ct, COUNT(*) AS c
        FROM attachments WHERE size_bytes = 0
        GROUP BY content_type ORDER BY c DESC LIMIT 15
        """
    ).fetchall()
    print("  By content_type (top 15):")
    for row in zero_by_content:
        print(f"    {row[0]!r}: {row[1]:,}")
    ext_expr = """
        LOWER(CASE
            WHEN instr(substr(filename, instr(filename, '.') + 1), '.') = 0
            THEN substr(filename, instr(filename, '.') + 1)
            WHEN instr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), '.') = 0
            THEN substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1)
            ELSE substr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), instr(substr(substr(filename, instr(filename, '.') + 1), instr(substr(filename, instr(filename, '.') + 1), '.') + 1), '.') + 1)
        END)
    """
    zero_by_ext = cur.execute(
        f"""
        SELECT {ext_expr} AS ext, COUNT(*) AS c
        FROM attachments
        WHERE size_bytes = 0 AND filename IS NOT NULL AND instr(filename, '.') > 0
        GROUP BY ext ORDER BY c DESC LIMIT 15
        """
    ).fetchall()
    print("  By extension (top 15):")
    for row in zero_by_ext:
        print(f"    .{row[0]}: {row[1]:,}")
    zero_by_inline = cur.execute(
        """
        SELECT COALESCE(is_inline, 0) AS inv, COUNT(*) AS c
        FROM attachments WHERE size_bytes = 0
        GROUP BY is_inline
        """
    ).fetchall()
    print("  By is_inline:")
    for row in zero_by_inline:
        label = "inline" if row[0] == 1 else "attachment"
        print(f"    {label}: {row[1]:,}")
    zero_business = cur.execute(
        """
        SELECT COUNT(*) FROM attachments
        WHERE size_bytes = 0
        AND (LOWER(content_type) LIKE 'application/pdf%'
             OR LOWER(filename) LIKE '%.pdf'
             OR LOWER(filename) GLOB '*.doc' OR LOWER(filename) GLOB '*.docx'
             OR LOWER(filename) GLOB '*.xls' OR LOWER(filename) GLOB '*.xlsx')
        """
    ).fetchone()[0]
    print(f"  Zero-byte among likely business docs (pdf/doc/xls/xlsx): {zero_business:,}")
    zero_samples = cur.execute(
        """
        SELECT filename, content_type, is_inline
        FROM attachments WHERE size_bytes = 0
        LIMIT 10
        """
    ).fetchall()
    print("  Sample filenames (up to 10):")
    for row in zero_samples:
        print(f"    {row[0]!r} | {row[1]!r} | is_inline={row[2]}")

    print("\n--- Sample attachments (PDF / Excel / Word / image) ---")
    for label, cond in [
        ("PDF", "LOWER(content_type) LIKE 'application/pdf%' OR LOWER(filename) LIKE '%.pdf'"),
        ("Excel", "LOWER(filename) GLOB '*.xls' OR LOWER(filename) GLOB '*.xlsx' OR LOWER(filename) GLOB '*.csv'"),
        ("Word", "LOWER(filename) GLOB '*.doc' OR LOWER(filename) GLOB '*.docx'"),
        ("Image", "LOWER(content_type) LIKE 'image/%'"),
    ]:
        print(f"\n[{label} attachments — sample up to 5]")
        q = f"""
        SELECT a.email_id, a.filename, a.content_type, a.size_bytes, e.subject
        FROM attachments a
        JOIN emails e ON e.id = a.email_id
        WHERE {cond}
        LIMIT 5
        """
        for row in cur.execute(q):
            print(
                f"  email_id={row['email_id']} size={row['size_bytes']} "
                f"type={row['content_type']!r} filename={row['filename']!r} subject={row['subject']!r}"
            )

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

