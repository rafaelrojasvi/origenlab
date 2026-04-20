#!/usr/bin/env python3
"""Read-only SQLite archive checks before Postgres migration (types, FKs, quality).

Does not modify the database. Connects with mode=ro and PRAGMA query_only=ON.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=60.0)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _normalize_iso_z(value: str) -> str:
    s = value.strip()
    if len(s) >= 1 and s[-1] in ("Z", "z"):
        return s[:-1] + "+00:00"
    return s


def parse_iso_timestamp(value: Any) -> bool:
    """Return True if value is parseable by datetime.fromisoformat after Z normalization."""
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    s = _normalize_iso_z(value)
    if not s:
        return False
    try:
        datetime.fromisoformat(s)
        return True
    except (TypeError, ValueError, OSError):
        return False


def is_bool01(value: Any) -> bool:
    """True if value is NULL or SQLite-safe 0/1 (integers only; bool is a distinct case)."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in (0, 1)
    return False


def _fetch_invalid_timestamp_samples(
    conn: sqlite3.Connection,
    *,
    table: str,
    col: str,
    id_col: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f'SELECT "{id_col}", "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL'
    ).fetchall()
    out: list[dict[str, Any]] = []
    for pk, raw in rows:
        if parse_iso_timestamp(raw):
            continue
        out.append({"id": pk, "value": raw})
        if len(out) >= limit:
            break
    return out


def _timestamp_check(
    conn: sqlite3.Connection,
    *,
    table: str,
    col: str,
    id_col: str,
    sample_limit: int,
) -> dict[str, Any]:
    non_null = int(
        conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL').fetchone()[0]
    )
    parseable = 0
    rows = conn.execute(
        f'SELECT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL'
    ).fetchall()
    for (raw,) in rows:
        if parse_iso_timestamp(raw):
            parseable += 1
    invalid = non_null - parseable
    samples = _fetch_invalid_timestamp_samples(
        conn, table=table, col=col, id_col=id_col, limit=sample_limit
    )
    return {
        "non_null": non_null,
        "parseable": parseable,
        "invalid": invalid,
        "invalid_samples": samples,
    }


def _boolean_check(
    conn: sqlite3.Connection,
    *,
    table: str,
    col: str,
    id_col: str,
    sample_limit: int,
) -> dict[str, Any]:
    total = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    bad: list[tuple[Any, Any]] = []
    for r in conn.execute(f'SELECT "{id_col}", "{col}" FROM "{table}"').fetchall():
        pk, val = r[0], r[1]
        if is_bool01(val):
            continue
        bad.append((pk, val))
    invalid = len(bad)
    samples = [{"id": pk, "value": val} for pk, val in bad[:sample_limit]]
    return {
        "row_count": total,
        "invalid": invalid,
        "invalid_samples": samples,
    }


def _safe_count(conn: sqlite3.Connection, table: str) -> int | None:
    if not _has_table(conn, table):
        return None
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def build_report(conn: sqlite3.Connection, *, sample_limit: int) -> dict[str, Any]:
    if not _has_table(conn, "emails"):
        raise RuntimeError("missing required table: emails")
    if not _has_table(conn, "attachments"):
        raise RuntimeError("missing required table: attachments")
    if not _has_table(conn, "attachment_extracts"):
        raise RuntimeError("missing required table: attachment_extracts")

    has_dm = _has_table(conn, "document_master")

    counts: dict[str, Any] = {
        "emails": _safe_count(conn, "emails"),
        "attachments": _safe_count(conn, "attachments"),
        "attachment_extracts": _safe_count(conn, "attachment_extracts"),
        "document_master": _safe_count(conn, "document_master"),
    }

    timestamp_checks: dict[str, Any] = {
        "emails.date_iso": _timestamp_check(
            conn, table="emails", col="date_iso", id_col="id", sample_limit=sample_limit
        ),
        "attachments.created_at": _timestamp_check(
            conn, table="attachments", col="created_at", id_col="id", sample_limit=sample_limit
        ),
        "attachment_extracts.created_at": _timestamp_check(
            conn,
            table="attachment_extracts",
            col="created_at",
            id_col="id",
            sample_limit=sample_limit,
        ),
    }
    if has_dm:
        timestamp_checks["document_master.sent_at"] = _timestamp_check(
            conn,
            table="document_master",
            col="sent_at",
            id_col="attachment_id",
            sample_limit=sample_limit,
        )

    boolean_checks: dict[str, Any] = {
        "emails.body_has_plain": _boolean_check(
            conn, table="emails", col="body_has_plain", id_col="id", sample_limit=sample_limit
        ),
        "emails.body_has_html": _boolean_check(
            conn, table="emails", col="body_has_html", id_col="id", sample_limit=sample_limit
        ),
        "emails.has_attachments": _boolean_check(
            conn, table="emails", col="has_attachments", id_col="id", sample_limit=sample_limit
        ),
        "attachments.is_inline": _boolean_check(
            conn, table="attachments", col="is_inline", id_col="id", sample_limit=sample_limit
        ),
        "attachment_extracts.has_quote_terms": _boolean_check(
            conn,
            table="attachment_extracts",
            col="has_quote_terms",
            id_col="id",
            sample_limit=sample_limit,
        ),
        "attachment_extracts.has_invoice_terms": _boolean_check(
            conn,
            table="attachment_extracts",
            col="has_invoice_terms",
            id_col="id",
            sample_limit=sample_limit,
        ),
        "attachment_extracts.has_price_list_terms": _boolean_check(
            conn,
            table="attachment_extracts",
            col="has_price_list_terms",
            id_col="id",
            sample_limit=sample_limit,
        ),
        "attachment_extracts.has_purchase_terms": _boolean_check(
            conn,
            table="attachment_extracts",
            col="has_purchase_terms",
            id_col="id",
            sample_limit=sample_limit,
        ),
    }
    if has_dm:
        for col in (
            "has_quote_terms",
            "has_invoice_terms",
            "has_purchase_terms",
            "has_price_list_terms",
        ):
            boolean_checks[f"document_master.{col}"] = _boolean_check(
                conn,
                table="document_master",
                col=col,
                id_col="attachment_id",
                sample_limit=sample_limit,
            )

    # Orphan FK checks
    orphan_attachments = conn.execute(
        """
        SELECT a.id, a.email_id
        FROM attachments a
        WHERE NOT EXISTS (SELECT 1 FROM emails e WHERE e.id = a.email_id)
        LIMIT ?
        """,
        (sample_limit,),
    ).fetchall()
    orphan_attachment_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM attachments a
            WHERE NOT EXISTS (SELECT 1 FROM emails e WHERE e.id = a.email_id)
            """
        ).fetchone()[0]
    )

    orphan_extracts = conn.execute(
        """
        SELECT x.id, x.attachment_id
        FROM attachment_extracts x
        WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = x.attachment_id)
        LIMIT ?
        """,
        (sample_limit,),
    ).fetchall()
    orphan_extract_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM attachment_extracts x
            WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = x.attachment_id)
            """
        ).fetchone()[0]
    )

    orphan_dm_att: list[tuple[Any, ...]] = []
    orphan_dm_att_count = 0
    orphan_dm_email: list[tuple[Any, ...]] = []
    orphan_dm_email_count = 0
    if has_dm:
        orphan_dm_att = conn.execute(
            """
            SELECT d.attachment_id, d.email_id
            FROM document_master d
            WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = d.attachment_id)
            LIMIT ?
            """,
            (sample_limit,),
        ).fetchall()
        orphan_dm_att_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM document_master d
                WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = d.attachment_id)
                """
            ).fetchone()[0]
        )
        orphan_dm_email = conn.execute(
            """
            SELECT d.attachment_id, d.email_id
            FROM document_master d
            WHERE d.email_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM emails e WHERE e.id = d.email_id)
            LIMIT ?
            """,
            (sample_limit,),
        ).fetchall()
        orphan_dm_email_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM document_master d
                WHERE d.email_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM emails e WHERE e.id = d.email_id)
                """
            ).fetchone()[0]
        )

    orphan_checks: dict[str, Any] = {
        "attachments_missing_email": {
            "count": orphan_attachment_count,
            "samples": [{"attachment_id": r[0], "email_id": r[1]} for r in orphan_attachments],
        },
        "attachment_extracts_missing_attachment": {
            "count": orphan_extract_count,
            "samples": [{"extract_id": r[0], "attachment_id": r[1]} for r in orphan_extracts],
        },
    }
    if has_dm:
        orphan_checks["document_master_missing_attachment"] = {
            "count": orphan_dm_att_count,
            "samples": [{"attachment_id": r[0], "email_id": r[1]} for r in orphan_dm_att],
        }
        orphan_checks["document_master_missing_email"] = {
            "count": orphan_dm_email_count,
            "samples": [{"attachment_id": r[0], "email_id": r[1]} for r in orphan_dm_email],
        }

    # Duplicate message_id (non-null, non-empty after trim)
    dup_extra = int(
        conn.execute(
            """
            SELECT COALESCE(SUM(cnt - 1), 0)
            FROM (
              SELECT COUNT(*) AS cnt
              FROM emails
              WHERE message_id IS NOT NULL AND TRIM(message_id) != ''
              GROUP BY message_id
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )
    dup_groups = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT message_id
              FROM emails
              WHERE message_id IS NOT NULL AND TRIM(message_id) != ''
              GROUP BY message_id
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    null_empty_source = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM emails
            WHERE source_file IS NULL OR TRIM(COALESCE(source_file, '')) = ''
            """
        ).fetchone()[0]
    )

    gmail_sent_folders = ("[Gmail]/Enviados", "[Gmail]/Sent Mail")
    gmail_sent_count = int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM emails
            WHERE source_file LIKE 'gmail:%'
              AND folder IN ({",".join("?" * len(gmail_sent_folders))})
            """,
            gmail_sent_folders,
        ).fetchone()[0]
    )

    gmail_folders = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT folder
            FROM emails
            WHERE source_file LIKE 'gmail:%'
            ORDER BY folder
            """
        ).fetchall()
    ]

    quality_checks: dict[str, Any] = {
        "duplicate_non_null_message_id_extra_rows": dup_extra,
        "duplicate_non_null_message_id_groups": dup_groups,
        "emails_null_or_empty_source_file": null_empty_source,
        "gmail_sent_rows": gmail_sent_count,
        "gmail_source_file_distinct_folders": gmail_folders,
    }

    dup_rows = conn.execute(
        """
        SELECT message_id, COUNT(*) AS c
        FROM emails
        WHERE message_id IS NOT NULL AND TRIM(message_id) != ''
        GROUP BY message_id
        HAVING COUNT(*) > 1
        ORDER BY c DESC
        LIMIT ?
        """,
        (sample_limit,),
    ).fetchall()
    samples: dict[str, Any] = {
        "duplicate_message_ids": [
            {"message_id": mid, "row_count": int(c)} for mid, c in dup_rows
        ],
    }

    strict_reasons: list[str] = []
    for _k, sec in timestamp_checks.items():
        if sec.get("invalid", 0) > 0:
            strict_reasons.append(f"invalid_timestamps:{_k}")
    for _k, sec in boolean_checks.items():
        if sec.get("invalid", 0) > 0:
            strict_reasons.append(f"invalid_booleans:{_k}")
    if orphan_attachment_count > 0:
        strict_reasons.append("orphan_attachments")
    if orphan_extract_count > 0:
        strict_reasons.append("orphan_attachment_extracts")
    if has_dm and orphan_dm_att_count > 0:
        strict_reasons.append("orphan_document_master_attachment")
    if has_dm and orphan_dm_email_count > 0:
        strict_reasons.append("orphan_document_master_email")
    if null_empty_source > 0:
        strict_reasons.append("emails_null_or_empty_source_file")

    ok = len(strict_reasons) == 0

    return {
        "ok": ok,
        "strict_reasons": strict_reasons,
        "counts": counts,
        "timestamp_checks": timestamp_checks,
        "boolean_checks": boolean_checks,
        "orphan_checks": orphan_checks,
        "quality_checks": quality_checks,
        "samples": samples,
    }


def resolve_db_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = (os.environ.get("ORIGENLAB_SQLITE_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return load_settings().resolved_sqlite_path()


def print_human_summary(report: dict[str, Any]) -> None:
    print("SQLite archive validation (read-only)")
    print("=" * 50)
    c = report["counts"]
    print("\nRow counts:")
    for k in ("emails", "attachments", "attachment_extracts", "document_master"):
        v = c.get(k)
        print(f"  {k}: {v if v is not None else '(table missing)'}")
    print("\nTimestamp checks (ISO-8601 via fromisoformat, Z → +00:00):")
    for name, sec in report["timestamp_checks"].items():
        print(
            f"  {name}: non_null={sec['non_null']} parseable={sec['parseable']} "
            f"invalid={sec['invalid']}"
        )
        for s in sec.get("invalid_samples", [])[:10]:
            print(f"    sample id={s.get('id')} value={s.get('value')!r}")
    print("\nBoolean checks (expect NULL or integer 0/1):")
    for name, sec in report["boolean_checks"].items():
        print(f"  {name}: rows={sec['row_count']} invalid={sec['invalid']}")
        for s in sec.get("invalid_samples", [])[:10]:
            print(f"    sample id={s.get('id')} value={s.get('value')!r}")
    print("\nOrphan FK checks:")
    for name, sec in report["orphan_checks"].items():
        print(f"  {name}: count={sec['count']}")
        for s in sec.get("samples", [])[:10]:
            print(f"    sample {s}")
    q = report["quality_checks"]
    print("\nQuality:")
    print(f"  duplicate non-null message_id extra rows: {q['duplicate_non_null_message_id_extra_rows']}")
    print(f"  duplicate non-null message_id groups: {q['duplicate_non_null_message_id_groups']}")
    print(f"  emails with NULL/empty source_file: {q['emails_null_or_empty_source_file']}")
    print(f"  Gmail Sent rows (gmail:% + Enviados/Sent Mail): {q['gmail_sent_rows']}")
    print("  distinct folders (gmail:% rows):")
    for f in q["gmail_source_file_distinct_folders"]:
        print(f"    - {f!r}")
    print(f"\nok (strict-clean): {report['ok']}")
    if report.get("strict_reasons"):
        print("strict would flag:", ", ".join(report["strict_reasons"]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None, help="SQLite path (else ORIGENLAB_SQLITE_PATH or settings)")
    p.add_argument("--json-out", type=Path, default=None, help="Write JSON report to this path")
    p.add_argument("--sample-limit", type=int, default=10, metavar="N", help="Max samples per category (default 10)")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if invalid timestamps/booleans, orphans, or NULL/empty source_file",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_limit = max(1, int(args.sample_limit))
    path = resolve_db_path(args.db)
    if not path.is_file():
        print(f"error: database file not found: {path}", file=sys.stderr)
        return 2
    try:
        conn = _connect_readonly(path)
    except sqlite3.Error as exc:
        print(f"error: could not open database: {exc}", file=sys.stderr)
        return 2
    try:
        report = build_report(conn, sample_limit=sample_limit)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    # JSON contract: omit internal strict_reasons from written file unless useful — user asked fixed keys.
    out_doc: dict[str, Any] = {
        "ok": report["ok"],
        "counts": report["counts"],
        "timestamp_checks": report["timestamp_checks"],
        "boolean_checks": report["boolean_checks"],
        "orphan_checks": report["orphan_checks"],
        "quality_checks": report["quality_checks"],
        "samples": report["samples"],
    }
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print_human_summary(report)

    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
