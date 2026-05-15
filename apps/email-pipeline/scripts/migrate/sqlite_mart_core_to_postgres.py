#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Writes to Postgres mart.contact_master,
# mart.organization_master, mart.opportunity_signals. --replace DELETEs those
# tables before reload. Use scratch/staging Postgres only.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Copy SQLite mart core tables into Postgres mart schema (dashboard API Slice 1).

Scope:
    - Reads SQLite in read-only mode.
    - Writes mart.contact_master, mart.organization_master, mart.opportunity_signals.
    - Does not modify SQLite or archive.* tables.

Behavior:
    - Missing SQLite source tables → warning, 0 rows loaded for that table.
    - Missing Postgres targets → hard failure (run Alembic head first).
    - Default refuses non-empty targets unless --replace.
    - --dry-run validates counts only.
    - Refuses non-scratch-looking Postgres URLs unless --allow-non-scratch-postgres.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.operational_scope import (
    sql_exclude_operational_noise_email,
    sqlite_contact_canonical_link_exists,
    sqlite_opportunity_signal_operational_predicate,
    sqlite_organization_canonical_link_exists,
)

_VALIDATE_PATH = REPO / "scripts" / "qa" / "validate_sqlite_archive_for_postgres.py"
_spec = importlib.util.spec_from_file_location("validate_sqlite_archive_for_postgres", _VALIDATE_PATH)
assert _spec and _spec.loader
_validate_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate_mod)
_connect_readonly = _validate_mod._connect_readonly
_normalize_iso_z = _validate_mod._normalize_iso_z

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Json = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

_SCRATCH_URL_TOKENS: tuple[str, ...] = (
    "scratch",
    "staging",
    "stage",
    "test",
    "dev",
    "local",
    "localhost",
    "127.0.0.1",
)

TABLE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "source": "contact_master",
        "target": "mart.contact_master",
        "pk": "email",
        "columns": (
            "email",
            "contact_name_best",
            "domain",
            "organization_name_guess",
            "organization_type_guess",
            "first_seen_at",
            "last_seen_at",
            "total_emails",
            "inbound_emails",
            "outbound_emails",
            "quote_email_count",
            "invoice_email_count",
            "purchase_email_count",
            "business_doc_email_count",
            "quote_doc_count",
            "invoice_doc_count",
            "top_equipment_tags",
            "confidence_score",
        ),
        "timestamp_columns": frozenset({"first_seen_at", "last_seen_at"}),
        "delete_order": 3,
    },
    {
        "source": "organization_master",
        "target": "mart.organization_master",
        "pk": "domain",
        "columns": (
            "domain",
            "organization_name_guess",
            "organization_type_guess",
            "first_seen_at",
            "last_seen_at",
            "total_emails",
            "total_contacts",
            "quote_email_count",
            "invoice_email_count",
            "purchase_email_count",
            "business_doc_email_count",
            "quote_doc_count",
            "invoice_doc_count",
            "top_equipment_tags",
            "key_contacts",
        ),
        "timestamp_columns": frozenset({"first_seen_at", "last_seen_at"}),
        "delete_order": 2,
    },
    {
        "source": "opportunity_signals",
        "target": "mart.opportunity_signals",
        "pk": "id",
        "columns": (
            "id",
            "signal_type",
            "entity_kind",
            "entity_key",
            "email_id",
            "attachment_id",
            "score",
            "details_json",
            "created_at",
        ),
        "timestamp_columns": frozenset({"created_at"}),
        "json_columns": frozenset({"details_json"}),
        "delete_order": 1,
        "reset_sequence": True,
    },
)

_CONTACT_COLS = TABLE_SPECS[0]["columns"]
_ORG_COLS = TABLE_SPECS[1]["columns"]
_OPP_COLS = TABLE_SPECS[2]["columns"]

_CANONICAL_CONTACT_SELECT = f"""
SELECT {", ".join(_CONTACT_COLS)}
FROM contact_master cm
WHERE {sqlite_contact_canonical_link_exists("cm")}
  AND {sql_exclude_operational_noise_email("cm.email")}
ORDER BY cm.email
"""

_CANONICAL_ORG_SELECT = f"""
SELECT {", ".join(_ORG_COLS)}
FROM organization_master om
WHERE {sqlite_organization_canonical_link_exists("om")}
  AND {sql_exclude_operational_noise_email("om.domain")}
ORDER BY om.domain
"""

_CANONICAL_OPP_SELECT = f"""
SELECT {", ".join(_OPP_COLS)}
FROM opportunity_signals os
WHERE {sqlite_opportunity_signal_operational_predicate("os")}
ORDER BY os.id
"""

CANONICAL_TABLE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "source": "contact_master_canonical",
        "target": "mart.contact_master_canonical",
        "pk": "email",
        "columns": _CONTACT_COLS,
        "timestamp_columns": frozenset({"first_seen_at", "last_seen_at"}),
        "source_select_sql": _CANONICAL_CONTACT_SELECT,
        "requires_tables": ("contact_master", "emails"),
        "delete_order": 6,
    },
    {
        "source": "organization_master_canonical",
        "target": "mart.organization_master_canonical",
        "pk": "domain",
        "columns": _ORG_COLS,
        "timestamp_columns": frozenset({"first_seen_at", "last_seen_at"}),
        "source_select_sql": _CANONICAL_ORG_SELECT,
        "requires_tables": ("organization_master", "contact_master", "emails"),
        "delete_order": 5,
    },
    {
        "source": "opportunity_signals_canonical",
        "target": "mart.opportunity_signals_canonical",
        "pk": "id",
        "columns": _OPP_COLS,
        "timestamp_columns": frozenset({"created_at"}),
        "json_columns": frozenset({"details_json"}),
        "source_select_sql": _CANONICAL_OPP_SELECT,
        "requires_tables": ("opportunity_signals", "emails"),
        "delete_order": 4,
        "reset_sequence": True,
    },
)

ALL_TABLE_SPECS: tuple[dict[str, Any], ...] = TABLE_SPECS + CANONICAL_TABLE_SPECS


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


def assert_scratch_postgres_target(pg_url: str, *, allow_non_scratch: bool) -> None:
    if allow_non_scratch:
        return
    low = pg_url.lower()
    if any(tok in low for tok in _SCRATCH_URL_TOKENS):
        return
    parsed = urlparse(pg_url)
    host = (parsed.hostname or "").lower()
    db = (parsed.path or "").lstrip("/").lower()
    if host in ("localhost", "127.0.0.1") or "scratch" in db or "staging" in db:
        return
    raise ValueError(
        "Postgres URL does not look like scratch/staging (no scratch/staging/test/dev/local). "
        "Pass --allow-non-scratch-postgres only when you intend a non-scratch target."
    )


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            "psycopg is required. Install: uv sync --group postgres "
            f"({_PSYCOPG_IMPORT_ERROR})"
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


def parse_jsonb_python(value: Any) -> Any:
    """Parse SQLite JSON text into a Python object (no psycopg adaptation)."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise ValueError("expected str, dict, list, or NULL for JSON")
    s = value.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {"raw": s}


def adapt_jsonb_for_postgres(value: Any) -> Any:
    """Return psycopg Json wrapper for JSONB columns; None stays None."""
    _require_psycopg()
    assert Json is not None
    if value is None:
        return None
    if isinstance(value, Json):
        return value
    parsed = parse_jsonb_python(value)
    if parsed is None:
        return None
    return Json(parsed)


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


def should_refuse_nonempty_targets(*, any_nonempty: bool, replace: bool, dry_run: bool) -> bool:
    return any_nonempty and not replace and not dry_run


def format_load_progress(
    *, pg_table: str, loaded_so_far: int, total: int, elapsed_s: float, batch_len: int
) -> str:
    pct = (100.0 * loaded_so_far / total) if total else 0.0
    return (
        f"loading {pg_table}: {loaded_so_far}/{total} ({pct:.1f}%) "
        f"elapsed={elapsed_s:.1f}s batch={batch_len}"
    )


def collect_sqlite_source_counts(
    conn: sqlite3.Connection, specs: tuple[dict[str, Any], ...]
) -> tuple[dict[str, int], list[str], dict[str, bool]]:
    counts: dict[str, int] = {}
    warnings: list[str] = []
    exists_map: dict[str, bool] = {}
    for spec in specs:
        src = str(spec["source"])
        required = tuple(spec.get("requires_tables") or (spec.get("source"),))
        if spec.get("source_select_sql"):
            missing = [t for t in required if not sqlite_has_table(conn, t)]
            exists_map[src] = not missing
            if missing:
                counts[src] = 0
                warnings.append(
                    f"SQLite canonical source unavailable for {src} "
                    f"(missing: {', '.join(missing)})"
                )
                continue
            sel = str(spec["source_select_sql"])
            counts[src] = int(
                conn.execute(f"SELECT COUNT(*) FROM ({sel})").fetchone()[0]
            )
            continue
        exists = sqlite_has_table(conn, src)
        exists_map[src] = exists
        if not exists:
            counts[src] = 0
            warnings.append(f"SQLite source table missing: {src} (treated as 0 rows)")
            continue
        counts[src] = int(conn.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])
    return counts, warnings, exists_map


def _convert_row(
    row: tuple[Any, ...],
    *,
    table: str,
    pk: str,
    columns: tuple[str, ...],
    timestamp_columns: frozenset[str],
    json_columns: frozenset[str],
) -> tuple[Any, ...]:
    out: list[Any] = []
    row_id = row[0] if row else None
    for i, col in enumerate(columns):
        v = row[i]
        if col in timestamp_columns:
            try:
                out.append(iso_text_to_datetime(v))
            except ValueError:
                raise ConversionError(table, row_id, col, v) from None
            continue
        if col in json_columns:
            try:
                out.append(adapt_jsonb_for_postgres(v))
            except ValueError:
                raise ConversionError(table, row_id, col, v) from None
            continue
        if col == pk and v is None:
            raise ConversionError(table, row_id, col, v)
        out.append(v)
    return tuple(out)


def _insert_sql(target: str, columns: tuple[str, ...]) -> str:
    cols = ", ".join(columns)
    vals = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {target} ({cols}) VALUES ({vals})"


def load_table(
    sconn: sqlite3.Connection,
    pconn: psycopg.Connection,
    *,
    spec: dict[str, Any],
    source_exists: bool,
    t_start: float,
    fetch_batch: int = 1000,
) -> int:
    if not source_exists:
        return 0

    source = str(spec["source"])
    target = str(spec["target"])
    pk = str(spec["pk"])
    columns = tuple(spec["columns"])
    timestamp_columns = frozenset(spec.get("timestamp_columns") or ())
    json_columns = frozenset(spec.get("json_columns") or ())
    select_sql = spec.get("source_select_sql")

    if select_sql:
        total = int(sconn.execute(f"SELECT COUNT(*) FROM ({select_sql})").fetchone()[0])
    else:
        total = int(sconn.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0])
    loaded = 0
    sql = _insert_sql(target, columns)
    scur = sconn.cursor()
    if select_sql:
        scur.execute(str(select_sql))
    else:
        scur.execute(f"SELECT {', '.join(columns)} FROM {source} ORDER BY {pk}")
    while True:
        rows = scur.fetchmany(fetch_batch)
        if not rows:
            break
        batch = [
            _convert_row(
                r,
                table=source,
                pk=pk,
                columns=columns,
                timestamp_columns=timestamp_columns,
                json_columns=json_columns,
            )
            for r in rows
        ]
        with pconn.cursor() as pcur:
            pcur.executemany(sql, batch)
        pconn.commit()
        loaded += len(batch)
        print(
            format_load_progress(
                pg_table=target,
                loaded_so_far=loaded,
                total=total,
                elapsed_s=time.monotonic() - t_start,
                batch_len=len(batch),
            ),
            flush=True,
        )
    return loaded


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--postgres-url", default=None)
    p.add_argument(
        "--replace",
        action="store_true",
        help="DELETE mart core targets before load (required when targets non-empty)",
    )
    p.add_argument("--dry-run", action="store_true", help="Validate only; no writes")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument(
        "--allow-non-scratch-postgres",
        action="store_true",
        help="Allow Postgres URLs that do not look like scratch/staging",
    )
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
    result = _empty_result()
    result["dry_run"] = bool(args.dry_run)
    result["replace"] = bool(args.replace)
    result["loaded"] = {str(spec["source"]): 0 for spec in ALL_TABLE_SPECS}

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

    sqlite_counts, warnings, exists_map = collect_sqlite_source_counts(sconn, ALL_TABLE_SPECS)
    result["sqlite_counts"] = sqlite_counts
    result["warnings"].extend(warnings)

    try:
        _require_psycopg()
        pg_url = resolve_postgres_url(args.postgres_url)
        assert_scratch_postgres_target(pg_url, allow_non_scratch=bool(args.allow_non_scratch_postgres))
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
            for spec in ALL_TABLE_SPECS:
                schema, table = str(spec["target"]).split(".", 1)
                if not pg_table_exists(cur, schema, table):
                    raise ValueError(
                        f"Postgres target missing: {spec['target']}. "
                        "Run: uv run alembic -c alembic.ini upgrade head"
                    )
            for spec in ALL_TABLE_SPECS:
                cur.execute(f"SELECT COUNT(*) FROM {spec['target']}")
                result["postgres_counts_before"][str(spec["source"])] = int(cur.fetchone()[0])

        any_nonempty = any(v > 0 for v in result["postgres_counts_before"].values())
        if should_refuse_nonempty_targets(
            any_nonempty=any_nonempty, replace=bool(args.replace), dry_run=bool(args.dry_run)
        ):
            sconn.close()
            result["errors"].append(
                "Target mart core tables are not empty. Use --replace to reload on scratch."
            )
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        if args.dry_run:
            result["ok"] = True
            result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
            sconn.close()
            _write_json(args.json_out, result)
            print("dry-run ok: mart core prechecks passed; no writes performed.")
            return 0

        if args.replace:
            with pconn.cursor() as cur:
                for spec in sorted(ALL_TABLE_SPECS, key=lambda s: int(s["delete_order"])):
                    cur.execute(f"DELETE FROM {spec['target']}")
                for seq_table in (
                    "mart.opportunity_signals",
                    "mart.opportunity_signals_canonical",
                ):
                    cur.execute(
                        f"""
                        SELECT setval(
                          pg_get_serial_sequence('{seq_table}', 'id'),
                          1,
                          false
                        )
                        """
                    )
            pconn.commit()

        for spec in ALL_TABLE_SPECS:
            src = str(spec["source"])
            loaded = load_table(
                sconn,
                pconn,
                spec=spec,
                source_exists=bool(exists_map[src]),
                t_start=t0,
            )
            result["loaded"][src] = loaded

        for seq_table in (
            "mart.opportunity_signals",
            "mart.opportunity_signals_canonical",
        ):
            with pconn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT setval(
                      pg_get_serial_sequence('{seq_table}', 'id'),
                      COALESCE((SELECT MAX(id) FROM {seq_table}), 1)
                    )
                    """
                )
            pconn.commit()

        with pconn.cursor() as cur:
            row_count_ok = True
            for spec in ALL_TABLE_SPECS:
                src = str(spec["source"])
                target = str(spec["target"])
                cur.execute(f"SELECT COUNT(*) FROM {target}")
                after = int(cur.fetchone()[0])
                result["postgres_counts_after"][src] = after
                if exists_map[src]:
                    row_count_ok = row_count_ok and (sqlite_counts[src] == after)
            result["validation"]["row_counts_match"] = row_count_ok
            result["ok"] = row_count_ok

        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        if not result["ok"]:
            result["errors"].append("Post-load validation failed for mart core migration.")
            sconn.close()
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        sconn.close()
        _write_json(args.json_out, result)
        print("migration completed:", json.dumps(result["loaded"], indent=2))
        return 0
    except (ConversionError, ValueError) as exc:
        result["errors"].append(str(exc))
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        sconn.close()
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 1
    finally:
        pconn.close()


if __name__ == "__main__":
    raise SystemExit(main())
