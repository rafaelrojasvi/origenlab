#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Writes to Postgres mart.document_master; --replace DELETEs
# the target table before reload. Verify --postgres-url before running.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Copy SQLite document_master into Postgres mart.document_master.

Scope:
    - Reads SQLite in read-only mode.
    - Writes only mart.document_master in Postgres.
    - Does not modify SQLite runtime or Alembic state.

Safety:
    - Default refuses to write if target table is non-empty.
    - --replace deletes mart.document_master only, then reloads.
    - --dry-run validates preconditions and counts, but writes nothing.

Commits:
    - Per-batch commits for lower memory and safer long runs.
    - Interrupted runs can leave partial rows; rerun with --replace.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings

_VALIDATE_PATH = REPO / "scripts" / "qa" / "validate_sqlite_archive_for_postgres.py"
_spec = importlib.util.spec_from_file_location("validate_sqlite_archive_for_postgres", _VALIDATE_PATH)
assert _spec and _spec.loader
_validate_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate_mod)
_connect_readonly = _validate_mod._connect_readonly
_normalize_iso_z = _validate_mod._normalize_iso_z

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

INTERRUPTED_LOAD_HINT = (
    "Per-batch commits: interrupted runs may leave partial mart.document_master rows. "
    "Rerun with --replace."
)


class ConversionError(Exception):
    def __init__(self, table: str, row_id: Any, column: str, value: Any) -> None:
        super().__init__(
            f"invalid conversion {table} id={row_id!r} column={column!r} value={value!r}"
        )


def normalize_postgres_url(url: str) -> str:
    u = url.strip()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if u.startswith(prefix):
            return "postgresql://" + u[len(prefix) :]
    return u


def resolve_sqlite_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = (os.environ.get("ORIGENLAB_SQLITE_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return load_settings().resolved_sqlite_path()


def resolve_postgres_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return normalize_postgres_url(explicit.strip())
    for key in ("ORIGENLAB_POSTGRES_URL", "ALEMBIC_DATABASE_URL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return normalize_postgres_url(v)
    raise ValueError(
        "Postgres URL required. Pass --postgres-url or set ORIGENLAB_POSTGRES_URL "
        "or ALEMBIC_DATABASE_URL."
    )


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            "psycopg is required for this script. Install the postgres group: "
            f"uv sync --group postgres ({_PSYCOPG_IMPORT_ERROR})"
        )


def iso_text_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected str or NULL")
    s = _normalize_iso_z(value.strip())
    if not s:
        raise ValueError("empty timestamp string")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def int_to_bool_or_none(value: Any, *, table: str, row_id: Any, column: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConversionError(table, row_id, column, value)
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ConversionError(table, row_id, column, value)


def sqlite_has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def pg_table_exists(cur: psycopg.Cursor, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def format_load_progress(
    *, pg_table: str, loaded_so_far: int, total: int, elapsed_s: float, batch_len: int
) -> str:
    pct = (100.0 * loaded_so_far / total) if total else 0.0
    return (
        f"loading {pg_table}: {loaded_so_far}/{total} ({pct:.1f}%) "
        f"elapsed={elapsed_s:.1f}s batch={batch_len}"
    )


def validate_sqlite_source(conn: sqlite3.Connection, *, sample_limit: int) -> dict[str, Any]:
    if not sqlite_has_table(conn, "document_master"):
        raise ValueError("SQLite source table missing: document_master")

    total = int(conn.execute("SELECT COUNT(*) FROM document_master").fetchone()[0])
    sent_non_null = int(
        conn.execute("SELECT COUNT(*) FROM document_master WHERE sent_at IS NOT NULL").fetchone()[0]
    )

    invalid_sent: list[dict[str, Any]] = []
    for aid, sent_at in conn.execute(
        "SELECT attachment_id, sent_at FROM document_master WHERE sent_at IS NOT NULL"
    ).fetchall():
        try:
            iso_text_to_datetime(sent_at)
        except ValueError:
            invalid_sent.append({"attachment_id": aid, "sent_at": sent_at})
            if len(invalid_sent) >= sample_limit:
                break
    invalid_sent_count = int(
        conn.execute("SELECT COUNT(*) FROM document_master WHERE sent_at IS NOT NULL").fetchone()[0]
    ) - (
        sent_non_null - len(invalid_sent)
    )
    # Recompute precisely for correctness:
    valid_sent = 0
    for (sent_at,) in conn.execute(
        "SELECT sent_at FROM document_master WHERE sent_at IS NOT NULL"
    ).fetchall():
        try:
            iso_text_to_datetime(sent_at)
            valid_sent += 1
        except ValueError:
            pass
    invalid_sent_count = sent_non_null - valid_sent

    bool_cols = (
        "has_quote_terms",
        "has_invoice_terms",
        "has_purchase_terms",
        "has_price_list_terms",
    )
    invalid_bool_count = 0
    invalid_bool_samples: list[dict[str, Any]] = []
    rows = conn.execute(
        """
        SELECT attachment_id, has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms
        FROM document_master
        """
    ).fetchall()
    for r in rows:
        aid = r[0]
        for i, col in enumerate(bool_cols):
            val = r[i + 1]
            try:
                int_to_bool_or_none(val, table="document_master", row_id=aid, column=col)
            except ConversionError:
                invalid_bool_count += 1
                if len(invalid_bool_samples) < sample_limit:
                    invalid_bool_samples.append({"attachment_id": aid, "column": col, "value": val})

    return {
        "row_count": total,
        "sent_at_non_null": sent_non_null,
        "sent_at_invalid_count": invalid_sent_count,
        "sent_at_invalid_samples": invalid_sent,
        "invalid_boolean_count": invalid_bool_count,
        "invalid_boolean_samples": invalid_bool_samples,
    }


def load_source_batch(
    conn: sqlite3.Connection, *, last_attachment_id: int, batch_size: int
) -> list[tuple[Any, ...]]:
    return conn.execute(
        """
        SELECT
          attachment_id, email_id, filename, extension, sender_email, sender_domain, recipient_domain,
          sent_at, doc_type, has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms,
          equipment_tags, extracted_preview_raw, extracted_preview_clean, preview_quality_score
        FROM document_master
        WHERE attachment_id > ?
        ORDER BY attachment_id
        LIMIT ?
        """,
        (last_attachment_id, batch_size),
    ).fetchall()


def row_to_pg_tuple(row: tuple[Any, ...]) -> tuple[Any, ...]:
    (
        attachment_id,
        email_id,
        filename,
        extension,
        sender_email,
        sender_domain,
        recipient_domain,
        sent_at,
        doc_type,
        has_quote_terms,
        has_invoice_terms,
        has_purchase_terms,
        has_price_list_terms,
        equipment_tags,
        extracted_preview_raw,
        extracted_preview_clean,
        preview_quality_score,
    ) = row
    try:
        sent_at_dt = iso_text_to_datetime(sent_at)
    except ValueError:
        raise ConversionError("document_master", attachment_id, "sent_at", sent_at) from None
    return (
        int(attachment_id),
        int(email_id) if email_id is not None else None,
        filename,
        extension,
        sender_email,
        sender_domain,
        recipient_domain,
        sent_at_dt,
        doc_type,
        int_to_bool_or_none(
            has_quote_terms, table="document_master", row_id=attachment_id, column="has_quote_terms"
        ),
        int_to_bool_or_none(
            has_invoice_terms, table="document_master", row_id=attachment_id, column="has_invoice_terms"
        ),
        int_to_bool_or_none(
            has_purchase_terms,
            table="document_master",
            row_id=attachment_id,
            column="has_purchase_terms",
        ),
        int_to_bool_or_none(
            has_price_list_terms,
            table="document_master",
            row_id=attachment_id,
            column="has_price_list_terms",
        ),
        equipment_tags,
        extracted_preview_raw,
        extracted_preview_clean,
        float(preview_quality_score) if preview_quality_score is not None else None,
    )


INSERT_SQL = """
INSERT INTO mart.document_master (
  attachment_id, email_id, filename, extension, sender_email, sender_domain, recipient_domain,
  sent_at, doc_type, has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms,
  equipment_tags, extracted_preview_raw, extracted_preview_clean, preview_quality_score
) VALUES (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def precheck_parent_coverage(
    sconn: sqlite3.Connection, pconn: psycopg.Connection, *, batch_size: int
) -> dict[str, int]:
    """Verify all source attachment_id/email_id have parent rows in Postgres archive."""
    missing_attachment = 0
    missing_email = 0
    last_id = 0
    while True:
        rows = sconn.execute(
            """
            SELECT attachment_id, email_id
            FROM document_master
            WHERE attachment_id > ?
            ORDER BY attachment_id
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break
        last_id = int(rows[-1][0])
        att_ids = [int(r[0]) for r in rows]
        email_ids = [int(r[1]) for r in rows if r[1] is not None]
        with pconn.cursor() as cur:
            cur.execute(
                "SELECT id FROM archive.attachments WHERE id = ANY(%s)",
                (att_ids,),
            )
            existing_att = {int(r[0]) for r in cur.fetchall()}
            missing_attachment += sum(1 for x in att_ids if x not in existing_att)
            if email_ids:
                cur.execute("SELECT id FROM archive.emails WHERE id = ANY(%s)", (email_ids,))
                existing_em = {int(r[0]) for r in cur.fetchall()}
                missing_email += sum(1 for x in email_ids if x not in existing_em)
        del rows
    return {"missing_attachment_parents": missing_attachment, "missing_email_parents": missing_email}


def pg_counts(cur: psycopg.Cursor) -> dict[str, int]:
    cur.execute("SELECT COUNT(*) FROM mart.document_master")
    dm = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM archive.attachments")
    att = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM archive.emails")
    em = int(cur.fetchone()[0])
    return {"mart.document_master": dm, "archive.attachments": att, "archive.emails": em}


def should_refuse_nonempty(*, target_nonempty: bool, replace: bool, dry_run: bool) -> bool:
    return target_nonempty and not replace and not dry_run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None, help="SQLite path (else env/settings)")
    p.add_argument(
        "--postgres-url",
        default=None,
        help="Postgres URL (else ORIGENLAB_POSTGRES_URL / ALEMBIC_DATABASE_URL)",
    )
    p.add_argument("--batch-size", type=int, default=500, metavar="N")
    p.add_argument("--replace", action="store_true", help="Delete mart.document_master before load")
    p.add_argument("--dry-run", action="store_true", help="Validate preconditions only; no writes")
    p.add_argument("--json-out", type=Path, default=None, help="Write JSON summary")
    p.add_argument("--sample-limit", type=int, default=10, metavar="N")
    return p


def _empty_result() -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": False,
        "replace": False,
        "sqlite_counts": {},
        "postgres_counts_before": {},
        "postgres_counts_after": {},
        "loaded": {},
        "validation": {},
        "errors": [],
        "warnings": [],
        "elapsed_seconds": 0.0,
    }


def _write_json(path: Path | None, doc: dict[str, Any]) -> None:
    if path is None:
        return
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    batch_size = max(1, int(args.batch_size))
    sample_limit = max(1, int(args.sample_limit))

    result = _empty_result()
    result["dry_run"] = bool(args.dry_run)
    result["replace"] = bool(args.replace)
    result["loaded"] = {"mart.document_master": 0}

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    if not sqlite_path.is_file():
        result["errors"].append(f"SQLite file not found: {sqlite_path}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        sconn = _connect_readonly(sqlite_path)
    except sqlite3.Error as exc:
        result["errors"].append(f"SQLite open failed: {exc}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        sqlite_metrics = validate_sqlite_source(sconn, sample_limit=sample_limit)
    except ValueError as exc:
        sconn.close()
        result["errors"].append(str(exc))
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2
    result["sqlite_counts"] = {"document_master": sqlite_metrics["row_count"]}
    if sqlite_metrics["sent_at_invalid_count"] > 0 or sqlite_metrics["invalid_boolean_count"] > 0:
        sconn.close()
        result["errors"].append("SQLite document_master failed strict conversion precheck.")
        result["validation"] = sqlite_metrics
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 1

    try:
        _require_psycopg()
        pg_url = resolve_postgres_url(args.postgres_url)
    except (RuntimeError, ValueError) as exc:
        sconn.close()
        result["errors"].append(str(exc))
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    assert psycopg is not None
    try:
        pconn = psycopg.connect(pg_url, autocommit=False)
    except Exception as exc:  # noqa: BLE001
        sconn.close()
        result["errors"].append(f"Postgres connect failed: {exc}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    t0 = time.monotonic()
    try:
        with pconn.cursor() as cur:
            # Target and parent table preconditions.
            if not pg_table_exists(cur, "mart", "document_master"):
                raise ValueError("Postgres target table missing: mart.document_master")
            for t in ("emails", "attachments"):
                if not pg_table_exists(cur, "archive", t):
                    raise ValueError(f"Postgres archive parent table missing: archive.{t}")
            before = pg_counts(cur)
        result["postgres_counts_before"] = before

        parent_check = precheck_parent_coverage(sconn, pconn, batch_size=batch_size)
        result["validation"]["parent_precheck"] = parent_check
        if parent_check["missing_attachment_parents"] > 0 or parent_check["missing_email_parents"] > 0:
            sconn.close()
            result["errors"].append("Postgres archive parent coverage check failed for source document_master.")
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        target_nonempty = before["mart.document_master"] > 0
        if should_refuse_nonempty(
            target_nonempty=target_nonempty, replace=bool(args.replace), dry_run=bool(args.dry_run)
        ):
            sconn.close()
            result["errors"].append(
                "mart.document_master is not empty. Use --replace to clear it before reload."
            )
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        if args.dry_run:
            sconn.close()
            result["ok"] = True
            result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
            result["validation"]["dry_run"] = "validated; no writes"
            _write_json(args.json_out, result)
            print("dry-run ok: document_master prechecks passed; no writes performed.")
            return 0

        if args.replace and target_nonempty:
            with pconn.cursor() as cur:
                cur.execute("DELETE FROM mart.document_master")
            pconn.commit()

        loaded = 0
        last_id = 0
        total = int(sqlite_metrics["row_count"])
        while True:
            rows = load_source_batch(sconn, last_attachment_id=last_id, batch_size=batch_size)
            if not rows:
                break
            batch_len = len(rows)
            last_row_id = int(rows[-1][0])
            try:
                batch = [row_to_pg_tuple(r) for r in rows]
                with pconn.cursor() as cur:
                    cur.executemany(INSERT_SQL, batch)
                pconn.commit()
            except ConversionError as exc:
                result["errors"].append(str(exc))
                result["warnings"].append(INTERRUPTED_LOAD_HINT)
                result["loaded"]["mart.document_master"] = loaded
                sconn.close()
                _write_json(args.json_out, result)
                print(result["errors"][-1], file=sys.stderr)
                return 1
            finally:
                del rows
                del batch
                gc.collect()

            loaded += batch_len
            last_id = last_row_id
            print(
                format_load_progress(
                    pg_table="mart.document_master",
                    loaded_so_far=loaded,
                    total=total,
                    elapsed_s=time.monotonic() - t0,
                    batch_len=batch_len,
                ),
                flush=True,
            )

        result["loaded"]["mart.document_master"] = loaded

        with pconn.cursor() as cur:
            after = pg_counts(cur)
            result["postgres_counts_after"] = after
            cur.execute("SELECT MIN(attachment_id), MAX(attachment_id) FROM mart.document_master")
            pg_min, pg_max = cur.fetchone()
            s_min, s_max = sconn.execute(
                "SELECT MIN(attachment_id), MAX(attachment_id) FROM document_master"
            ).fetchone()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mart.document_master d
                WHERE NOT EXISTS (SELECT 1 FROM archive.attachments a WHERE a.id = d.attachment_id)
                """
            )
            orphan_att = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mart.document_master d
                WHERE d.email_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM archive.emails e WHERE e.id = d.email_id)
                """
            )
            orphan_email = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM mart.document_master WHERE sent_at IS NOT NULL")
            pg_sent_non_null = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT doc_type, COUNT(*) AS c
                FROM mart.document_master
                GROUP BY doc_type
                ORDER BY c DESC, doc_type
                LIMIT 20
                """
            )
            doc_type_dist = [{"doc_type": r[0], "count": int(r[1])} for r in cur.fetchall()]

        row_count_ok = after["mart.document_master"] == sqlite_metrics["row_count"]
        min_max_ok = (pg_min == s_min) and (pg_max == s_max)
        sent_non_null_ok = pg_sent_non_null == sqlite_metrics["sent_at_non_null"]
        val_ok = row_count_ok and min_max_ok and orphan_att == 0 and orphan_email == 0 and sent_non_null_ok
        result["validation"].update(
            {
                "row_count_match": row_count_ok,
                "attachment_id_min_max": {
                    "sqlite": {"min": s_min, "max": s_max},
                    "postgres": {"min": pg_min, "max": pg_max},
                    "match": min_max_ok,
                },
                "orphan_attachment_refs": orphan_att,
                "orphan_email_refs": orphan_email,
                "sent_at_non_null": {
                    "sqlite": sqlite_metrics["sent_at_non_null"],
                    "postgres": pg_sent_non_null,
                    "match": sent_non_null_ok,
                },
                "doc_type_distribution_top20": doc_type_dist,
                "invalid_boolean_count_precheck": sqlite_metrics["invalid_boolean_count"],
            }
        )
        result["ok"] = val_ok
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        if not val_ok:
            result["errors"].append("Post-load validation failed for mart.document_master.")
            result["warnings"].append(INTERRUPTED_LOAD_HINT)
            sconn.close()
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        sconn.close()
        _write_json(args.json_out, result)
        print("migration completed:", json.dumps(result["loaded"], indent=2))
        return 0
    except ValueError as exc:
        result["errors"].append(str(exc))
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2
    finally:
        pconn.close()


if __name__ == "__main__":
    raise SystemExit(main())
