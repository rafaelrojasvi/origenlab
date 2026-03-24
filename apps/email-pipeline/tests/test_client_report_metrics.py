"""SQLite-backed tests for client report metric helpers (src)."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.client_report_metrics import (
    merged_aggregate_sql,
    run_attachment_extract_metrics,
    run_attachment_metrics,
    run_merged_aggregate,
    run_year_cotiz_only,
    run_year_counts,
)


def _emails_ddl() -> str:
    return """
    CREATE TABLE emails (
        id INTEGER PRIMARY KEY,
        subject TEXT,
        body TEXT,
        sender TEXT,
        recipients TEXT,
        date_iso TEXT,
        has_attachments INTEGER,
        top_reply_clean TEXT
    );
    """


def test_run_merged_aggregate_counts(tmp_path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_emails_ddl())
    conn.execute(
        "INSERT INTO emails VALUES (1,'cotizacion','body','a@x.com',NULL,'2021-06-01',0,NULL)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (2,'x','microscopio y mas','b@y.com',NULL,'2021-07-01',0,NULL)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (3,'delivery failed','','mailer-daemon@z.com',NULL,NULL,0,NULL)"
    )
    conn.commit()
    agg = run_merged_aggregate(conn)
    conn.close()
    assert agg["total"] == 3
    assert agg["cotizacion"] == 1
    assert agg["eq_microscopio"] == 1
    assert agg["bounce_like"] == 1
    assert agg["with_date"] == 2


def test_run_year_counts_and_cotiz(tmp_path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_emails_ddl())
    conn.execute("INSERT INTO emails VALUES (1,'c','cotiz','',NULL,'2020-01-01',0,NULL)")
    conn.execute("INSERT INTO emails VALUES (2,'','other','',NULL,'2020-02-01',0,NULL)")
    conn.commit()
    assert run_year_counts(conn) == [{"year": "2020", "count": 2}]
    assert run_year_cotiz_only(conn) == [{"year": "2020", "count": 1}]
    conn.close()


def test_merged_aggregate_sql_contains_expected_columns():
    s = merged_aggregate_sql()
    assert "FROM emails" in s
    assert "cotiz_microscopio" in s


def test_run_attachment_metrics_none_without_attachments_table(tmp_path):
    db = tmp_path / "e.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_emails_ddl())
    conn.commit()
    conn.close()
    assert run_attachment_metrics(db.resolve()) is None


def test_run_attachment_metrics_with_pdf_and_cotiz_subject(tmp_path):
    db = tmp_path / "a.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_emails_ddl())
    conn.execute(
        """
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY,
            email_id INTEGER NOT NULL,
            part_index INTEGER NOT NULL,
            filename TEXT,
            content_type TEXT,
            is_inline INTEGER
        );
        """
    )
    conn.execute(
        "INSERT INTO emails VALUES (1,'cotización',NULL,'u@v.com',NULL,'2024-01-01',1,NULL)"
    )
    conn.execute(
        "INSERT INTO attachments VALUES (1,1,0,'q.pdf','application/pdf',0)"
    )
    conn.commit()
    conn.close()
    m = run_attachment_metrics(db.resolve())
    assert m is not None
    assert m["emails_with_attachments"] == 1
    assert m["emails_with_business_doc_attachments"] == 1
    assert m["cotizacion_emails_with_business_doc_attachments"] == 1
    assert m["attachment_counts_by_broad_class"]["pdf"] >= 1


def test_run_attachment_extract_metrics(tmp_path):
    db = tmp_path / "x.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE attachment_extracts (
            id INTEGER PRIMARY KEY,
            attachment_id INTEGER NOT NULL,
            extract_status TEXT NOT NULL,
            extract_method TEXT NOT NULL,
            detected_doc_type TEXT,
            has_quote_terms INTEGER,
            has_invoice_terms INTEGER,
            has_price_list_terms INTEGER,
            has_purchase_terms INTEGER
        );
        """
    )
    conn.execute(
        "INSERT INTO attachment_extracts VALUES (1,1,'success','pdf_text','invoice',1,0,0,0)"
    )
    conn.execute(
        "INSERT INTO attachment_extracts VALUES (2,2,'skipped','',NULL,0,0,0,0)"
    )
    conn.commit()
    conn.close()
    m = run_attachment_extract_metrics(db.resolve())
    assert m is not None
    assert m["extracts_total"] == 2
    assert m["by_status"]["success"] == 1
    assert m["by_status"]["skipped"] == 1
    assert m["signal_counts_success"]["has_quote_terms"] == 1
