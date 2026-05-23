"""Orchestrate SQLite → Postgres dashboard mirror sync (read-only SQLite, scratch-safe Postgres)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse, urlunparse

from origenlab_email_pipeline.classification_postgres_mirror import (
    sync_email_classification_canonical,
)
from origenlab_email_pipeline.commercial_purchase_postgres_mirror import (
    sync_commercial_purchase_events,
)
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.equipment_opportunity_mirror import (
    apply_load as apply_equipment_opportunity_mirror,
    preview_load as preview_equipment_opportunity_mirror,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (
    assert_scratch_postgres_target,
    connect_sqlite_readonly,
    resolve_postgres_url,
    resolve_sqlite_path,
)
from origenlab_email_pipeline.warm_case_promotion import (
    apply_promotion as apply_warm_case_promotion,
    preview_promotion as preview_warm_case_promotion,
)

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Json = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

EXPECTED_ALEMBIC_HEAD = "20260519_0016"
DASHBOARD_SYNC_KV_KEY = "dashboard_postgres_mirror_last_sync"

OUTBOUND_SCRIPT = "scripts/migrate/sqlite_outbound_sidecars_to_postgres.py"
MART_SCRIPT = "scripts/migrate/sqlite_mart_core_to_postgres.py"

OnlyMode = Literal["outbound", "mart", "canonical"]

REQUIRED_MIRROR_TABLES: tuple[tuple[str, str], ...] = (
    ("outbound", "contact_email_suppression"),
    ("outbound", "contact_domain_suppression"),
    ("outbound", "outreach_contact_state"),
    ("mart", "contact_master"),
    ("mart", "organization_master"),
    ("mart", "opportunity_signals"),
    ("mart", "contact_master_canonical"),
    ("mart", "organization_master_canonical"),
    ("mart", "opportunity_signals_canonical"),
)

REPORTING_WATERMARK_TABLE: tuple[str, str] = ("reporting", "dashboard_sync_run")

# SQLite mart tables read by mart_core loader (--replace). Guard before any Postgres mart wipe.
REQUIRED_SQLITE_MART_TABLES: tuple[str, ...] = (
    "contact_master",
    "organization_master",
    "opportunity_signals",
)


@dataclass(frozen=True)
class LoaderStep:
    name: str
    script_relpath: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class SqliteMartSourceCounts:
    canonical_gmail_email_count: int
    mart_table_counts: dict[str, int]


def redact_postgres_url(url: str) -> str:
    """Return URL safe for logs/watermarks (password removed)."""
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return "<invalid-url>"
    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostpart = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0] if userinfo else ""
        netloc = f"{user}:***@{hostpart}" if user else f"***@{hostpart}"
    redacted = parsed._replace(netloc=netloc)
    return urlunparse(redacted)


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def phase_log(message: str, *, log: Callable[[str], None] | None = None) -> None:
    sink = log or (lambda m: print(m, flush=True))
    sink(message)


def pg_table_exists(cur: Any, *, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def fetch_alembic_version(cur: Any) -> str | None:
    if not pg_table_exists(cur, schema="public", table="alembic_version"):
        return None
    cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
    row = cur.fetchone()
    if not row:
        return None
    return str(row[0] if not isinstance(row, dict) else row.get("version_num"))


def check_alembic_head(cur: Any) -> tuple[bool, str | None, str]:
    version = fetch_alembic_version(cur)
    if version is None:
        return False, None, "alembic_version table missing or empty (run: uv run alembic upgrade head)"
    if version != EXPECTED_ALEMBIC_HEAD:
        return (
            False,
            version,
            f"Alembic head mismatch: database={version!r} expected={EXPECTED_ALEMBIC_HEAD!r}",
        )
    return True, version, ""


def list_missing_tables(cur: Any, tables: tuple[tuple[str, str], ...]) -> list[str]:
    missing: list[str] = []
    for schema, table in tables:
        if not pg_table_exists(cur, schema=schema, table=table):
            missing.append(f"{schema}.{table}")
    return missing


def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def _sqlite_table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _sqlite_table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0] if row else 0)


def count_canonical_gmail_emails(conn: sqlite3.Connection) -> int:
    if not _sqlite_table_exists(conn, "emails"):
        return 0
    pred = sql_predicate_contacto_gmail_source(table_alias=None, coalesce_null=False)
    row = conn.execute(f"SELECT COUNT(*) FROM emails WHERE {pred}").fetchone()
    return int(row[0] if row else 0)


def collect_sqlite_mart_source_counts(sqlite_path: Path) -> SqliteMartSourceCounts:
    """Read-only counts from SQLite before mirroring mart tables to Postgres."""
    conn = connect_sqlite_readonly(sqlite_path)
    try:
        canonical = count_canonical_gmail_emails(conn)
        mart_counts = {t: _sqlite_table_count(conn, t) for t in REQUIRED_SQLITE_MART_TABLES}
    finally:
        conn.close()
    return SqliteMartSourceCounts(
        canonical_gmail_email_count=canonical,
        mart_table_counts=mart_counts,
    )


def assert_sqlite_mart_ready_for_mirror_sync(
    sqlite_path: Path,
    *,
    allow_empty_mart: bool = False,
) -> SqliteMartSourceCounts:
    """Fail closed when canonical Gmail exists but SQLite mart tables are empty."""
    counts = collect_sqlite_mart_source_counts(sqlite_path)
    if allow_empty_mart or counts.canonical_gmail_email_count == 0:
        return counts

    empty_tables = [t for t in REQUIRED_SQLITE_MART_TABLES if counts.mart_table_counts.get(t, 0) == 0]
    if not empty_tables:
        return counts

    listed = ", ".join(empty_tables)
    raise ValueError(
        "Refusing Postgres dashboard mirror sync: SQLite has "
        f"{counts.canonical_gmail_email_count} canonical Gmail email row(s) "
        f"(source_file LIKE 'gmail:contacto@origenlab.cl/%') but mart table(s) "
        f"{listed} are empty. This usually indicates a failed or incomplete "
        "build_business_mart.py --rebuild. Rebuild the mart on SQLite first, or pass "
        "--allow-empty-mart (break-glass only; may replace good Postgres mirror data "
        "with empty mart loads)."
    )


def mart_loader_planned(steps: list[LoaderStep]) -> bool:
    return any(step.name == "mart_core" for step in steps)


def preflight_sqlite(sqlite_path: Path) -> None:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")
    conn = connect_sqlite_readonly(sqlite_path)
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()


def preflight_postgres(pg_url: str) -> tuple[str, list[str]]:
    _require_psycopg()
    assert psycopg is not None
    missing_reporting: list[str] = []
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            ok, version, msg = check_alembic_head(cur)
            if not ok:
                raise ValueError(msg)
            missing = list_missing_tables(cur, REQUIRED_MIRROR_TABLES)
            if missing:
                raise ValueError(
                    "Postgres mirror tables missing: "
                    + ", ".join(missing)
                    + " (run: uv run alembic -c alembic.ini upgrade head)"
                )
            if not pg_table_exists(
                cur,
                schema=REPORTING_WATERMARK_TABLE[0],
                table=REPORTING_WATERMARK_TABLE[1],
            ):
                missing_reporting.append(
                    f"{REPORTING_WATERMARK_TABLE[0]}.{REPORTING_WATERMARK_TABLE[1]}"
                )
    return version or EXPECTED_ALEMBIC_HEAD, missing_reporting


def collect_mirror_counts(pg_url: str) -> dict[str, int]:
    _require_psycopg()
    assert psycopg is not None
    keys = {
        "canonical_contact_count": "mart.contact_master_canonical",
        "canonical_organization_count": "mart.organization_master_canonical",
        "canonical_opportunity_signal_count": "mart.opportunity_signals_canonical",
        "archive_contact_count": "mart.contact_master",
        "archive_organization_count": "mart.organization_master",
        "archive_opportunity_signal_count": "mart.opportunity_signals",
        "email_suppression_count": "outbound.contact_email_suppression",
        "domain_suppression_count": "outbound.contact_domain_suppression",
        "outreach_state_count": "outbound.outreach_contact_state",
        "commercial_purchase_event_count": "commercial.purchase_event",
        "commercial_purchase_event_item_count": "commercial.purchase_event_item",
    }
    out: dict[str, int] = {}
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            for key, qualified in keys.items():
                schema, table = qualified.split(".", 1)
                if not pg_table_exists(cur, schema=schema, table=table):
                    out[key] = 0
                    continue
                cur.execute(f"SELECT COUNT(*)::bigint FROM {qualified}")
                row = cur.fetchone()
                out[key] = int(row[0] if not isinstance(row, dict) else row["count"])
    return out


def plan_loader_steps(
    *,
    only: OnlyMode | None,
    skip_outbound: bool,
    skip_mart: bool,
) -> list[LoaderStep]:
    steps: list[LoaderStep] = []
    run_outbound = only == "outbound" or (only is None and not skip_outbound)
    run_mart = only in ("mart", "canonical") or (only is None and not skip_mart)
    if only == "canonical":
        mart_tables = "canonical"
    else:
        mart_tables = "all"
    if run_outbound and only not in ("mart", "canonical"):
        steps.append(
            LoaderStep(
                name="outbound_sidecars",
                script_relpath=OUTBOUND_SCRIPT,
                argv=("--replace",),
            )
        )
    if run_mart and only != "outbound":
        steps.append(
            LoaderStep(
                name="mart_core",
                script_relpath=MART_SCRIPT,
                argv=("--replace", "--tables", mart_tables),
            )
        )
    if not steps:
        raise ValueError("No loader steps selected (check --only / --skip-* flags).")
    return steps


def build_loader_command(
    repo_root: Path,
    step: LoaderStep,
    *,
    sqlite_path: Path,
    postgres_url: str,
    allow_non_scratch: bool,
) -> list[str]:
    script = repo_root / step.script_relpath
    cmd = [
        sys.executable,
        str(script),
        *step.argv,
        "--sqlite-db",
        str(sqlite_path),
        "--postgres-url",
        postgres_url,
    ]
    if allow_non_scratch and step.script_relpath == MART_SCRIPT:
        cmd.append("--allow-non-scratch-postgres")
    return cmd


def run_loader_subprocess(cmd: list[str], *, repo_root: Path) -> int:
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        check=False,
    )
    return int(proc.returncode)


def write_sync_watermark(
    pg_url: str,
    *,
    sqlite_path: Path,
    postgres_url_redacted: str,
    status: str,
    started_at: datetime,
    finished_at: datetime | None,
    counts: dict[str, int],
    error_message: str | None,
    details: dict[str, Any],
    dry_run: bool,
) -> int | None:
    if dry_run:
        return None
    _require_psycopg()
    assert psycopg is not None and Json is not None
    sync_id: int | None = None
    with psycopg.connect(pg_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            if pg_table_exists(
                cur,
                schema=REPORTING_WATERMARK_TABLE[0],
                table=REPORTING_WATERMARK_TABLE[1],
            ):
                cur.execute(
                    """
                    INSERT INTO reporting.dashboard_sync_run (
                      started_at, finished_at, status,
                      sqlite_path, postgres_url_redacted,
                      canonical_contact_count, canonical_organization_count,
                      canonical_opportunity_signal_count,
                      archive_contact_count, archive_organization_count,
                      archive_opportunity_signal_count,
                      email_suppression_count, domain_suppression_count,
                      outreach_state_count,
                      error_message, details_json
                    ) VALUES (
                      %s, %s, %s,
                      %s, %s,
                      %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s,
                      %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        started_at,
                        finished_at,
                        status,
                        str(sqlite_path),
                        postgres_url_redacted,
                        counts.get("canonical_contact_count"),
                        counts.get("canonical_organization_count"),
                        counts.get("canonical_opportunity_signal_count"),
                        counts.get("archive_contact_count"),
                        counts.get("archive_organization_count"),
                        counts.get("archive_opportunity_signal_count"),
                        counts.get("email_suppression_count"),
                        counts.get("domain_suppression_count"),
                        counts.get("outreach_state_count"),
                        error_message,
                        Json(details),
                    ),
                )
                row = cur.fetchone()
                sync_id = int(row[0] if not isinstance(row, dict) else row["id"])
            if pg_table_exists(cur, schema="ops", table="pipeline_kv"):
                kv_payload = {
                    "status": status,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat() if finished_at else None,
                    "sqlite_path": str(sqlite_path),
                    "postgres_url_redacted": postgres_url_redacted,
                    "counts": counts,
                    "sync_run_id": sync_id,
                    "details": details,
                }
                cur.execute(
                    """
                    INSERT INTO ops.pipeline_kv (kv_key, value_json, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (kv_key) DO UPDATE SET
                      value_json = EXCLUDED.value_json,
                      updated_at = now()
                    """,
                    (DASHBOARD_SYNC_KV_KEY, Json(kv_payload)),
                )
        conn.commit()
    return sync_id


def update_sync_run_details(
    pg_url: str,
    sync_run_id: int,
    details: dict[str, Any],
) -> None:
    _require_psycopg()
    assert psycopg is not None and Json is not None
    with psycopg.connect(pg_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            if pg_table_exists(
                cur,
                schema=REPORTING_WATERMARK_TABLE[0],
                table=REPORTING_WATERMARK_TABLE[1],
            ):
                cur.execute(
                    """
                    UPDATE reporting.dashboard_sync_run
                    SET details_json = %s
                    WHERE id = %s
                    """,
                    (Json(details), sync_run_id),
                )
        conn.commit()


def default_active_current_dir(repo_root: Path) -> Path:
    return (repo_root / "reports" / "out" / "active" / "current").resolve()


def validate_optional_loader_audit(
    *,
    include_equipment: bool,
    include_warm_cases: bool,
    dry_run: bool,
    updated_by: str | None,
    reason: str | None,
) -> None:
    if dry_run or not (include_equipment or include_warm_cases):
        return
    if not (updated_by and str(updated_by).strip()):
        raise ValueError(
            "Optional DB-2 loaders on apply require --updated-by (or --operator)."
        )
    if not (reason and str(reason).strip()):
        raise ValueError("Optional DB-2 loaders on apply require --reason.")


def _raise_if_optional_loader_failed(loader_name: str, summary: dict[str, Any]) -> None:
    if summary.get("dry_run"):
        return
    error = summary.get("error")
    if error:
        raise RuntimeError(f"{loader_name} failed: {error}")
    if not summary.get("applied"):
        warning = summary.get("warning")
        if loader_name == "warm_case_promotion" and warning == "no_candidates":
            return
        if loader_name == "equipment_opportunity_mirror" and warning == "empty_csv":
            return
        if (
            loader_name == "equipment_opportunity_mirror"
            and summary.get("idempotent") == "canonical_source_already_loaded"
            and summary.get("is_canonical") is True
        ):
            return
        raise RuntimeError(f"{loader_name} apply did not complete: {summary!r}")


def merge_optional_loader_details(
    details: dict[str, Any],
    *,
    equipment_summary: dict[str, Any] | None,
    warm_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(details)
    if equipment_summary is not None:
        merged["equipment_opportunity_sync"] = equipment_summary
        if equipment_summary.get("source_id") is not None:
            merged["equipment_opportunity_source_id"] = equipment_summary["source_id"]
        row_count = equipment_summary.get("rows_inserted")
        if row_count is None:
            row_count = equipment_summary.get("row_count")
        if row_count is not None:
            merged["equipment_opportunity_row_count"] = row_count
    if warm_summary is not None:
        merged["warm_case_sync"] = warm_summary
        if warm_summary.get("inserted_cases") is not None:
            merged["warm_case_inserted_count"] = warm_summary["inserted_cases"]
        if warm_summary.get("updated_cases") is not None:
            merged["warm_case_updated_count"] = warm_summary["updated_cases"]
        linked = warm_summary.get("linked_emails")
        if linked is not None:
            merged["warm_case_linked_email_count"] = linked
    return merged


def run_equipment_opportunity_sync(
    pg_url: str,
    repo_root: Path,
    *,
    dry_run: bool,
    updated_by: str | None,
    reason: str | None,
    sync_run_id: int | None,
) -> dict[str, Any]:
    active_current = default_active_current_dir(repo_root)
    if dry_run:
        return preview_equipment_opportunity_mirror(
            active_current,
            pg_url=pg_url,
        )
    return apply_equipment_opportunity_mirror(
        pg_url,
        active_current,
        updated_by=str(updated_by or "").strip(),
        reason=str(reason or "").strip(),
        sync_run_id=sync_run_id,
    )


def run_warm_case_promotion_sync(
    pg_url: str,
    sqlite_path: Path,
    *,
    dry_run: bool,
    updated_by: str | None,
    reason: str | None,
    days_window: int = 30,
    limit: int = 200,
) -> dict[str, Any]:
    if dry_run:
        return preview_warm_case_promotion(
            sqlite_path,
            days_window=days_window,
            limit=limit,
            pg_url=pg_url,
        )
    return apply_warm_case_promotion(
        pg_url,
        sqlite_path,
        days_window=days_window,
        limit=limit,
        updated_by=str(updated_by or "").strip(),
        reason=str(reason or "").strip(),
    )


def run_optional_db2_loaders(
    *,
    args: argparse.Namespace,
    pg_url: str,
    sqlite_path: Path,
    repo_root: Path,
    sync_run_id: int | None,
    dry_run: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    equipment_summary: dict[str, Any] | None = None
    warm_summary: dict[str, Any] | None = None

    if args.include_equipment_opportunities:
        equipment_summary = run_equipment_opportunity_sync(
            pg_url,
            repo_root,
            dry_run=dry_run,
            updated_by=args.updated_by,
            reason=args.reason,
            sync_run_id=sync_run_id,
        )
        _raise_if_optional_loader_failed("equipment_opportunity_mirror", equipment_summary)

    if args.include_warm_cases:
        warm_summary = run_warm_case_promotion_sync(
            pg_url,
            sqlite_path,
            dry_run=dry_run,
            updated_by=args.updated_by,
            reason=args.reason,
        )
        _raise_if_optional_loader_failed("warm_case_promotion", warm_summary)

    return equipment_summary, warm_summary


def format_summary_text(result: dict[str, Any]) -> str:
    c = result.get("counts") or {}
    lines = [
        "[sync] dashboard Postgres mirror",
        f"  status: {result.get('status')}",
        f"  dry_run: {result.get('dry_run')}",
        f"  elapsed_seconds: {result.get('elapsed_seconds')}",
        "  canonical:",
        f"    contacts: {c.get('canonical_contact_count')}",
        f"    organizations: {c.get('canonical_organization_count')}",
        f"    opportunity_signals: {c.get('canonical_opportunity_signal_count')}",
        "  archive:",
        f"    contacts: {c.get('archive_contact_count')}",
        f"    organizations: {c.get('archive_organization_count')}",
        f"    opportunity_signals: {c.get('archive_opportunity_signal_count')}",
        "  outbound:",
        f"    email_suppressions: {c.get('email_suppression_count')}",
        f"    domain_suppressions: {c.get('domain_suppression_count')}",
        f"    outreach_state: {c.get('outreach_state_count')}",
        "  commercial:",
        f"    purchase_events: {c.get('commercial_purchase_event_count')}",
        f"    purchase_event_items: {c.get('commercial_purchase_event_item_count')}",
    ]
    if result.get("sync_run_id") is not None:
        lines.append(f"  sync_run_id: {result.get('sync_run_id')}")
    if result.get("errors"):
        lines.append(f"  errors: {result['errors']}")
    lines.extend(
        [
            "",
            "API smoke (apps/api :8001 mirror — preferred; after uvicorn + ORIGENLAB_POSTGRES_URL):",
            "  curl -sS 'http://127.0.0.1:8001/mirror/dashboard/summary' | uv run python -m json.tool",
            "  curl -sS 'http://127.0.0.1:8001/mirror/dashboard/summary?scope=archive' | uv run python -m json.tool",
            "  curl -sS 'http://127.0.0.1:8001/mirror/meta/dashboard-sync' | uv run python -m json.tool",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Refresh Postgres dashboard mirror from SQLite (read-only). "
            "Runs outbound sidecars then mart core loaders."
        )
    )
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--postgres-url", default=None)
    p.add_argument("--dry-run", action="store_true", help="Preflight only; no loader writes")
    p.add_argument("--only", choices=("outbound", "mart", "canonical"), default=None)
    p.add_argument("--skip-outbound", action="store_true")
    p.add_argument("--skip-mart", action="store_true")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument(
        "--allow-non-scratch-postgres",
        action="store_true",
        help="Pass through to mart loader when target is not scratch/staging",
    )
    p.add_argument(
        "--allow-empty-mart",
        action="store_true",
        help=(
            "Break-glass: skip SQLite mart empty check before --replace loaders. "
            "May wipe good Postgres dashboard mart data if mart rebuild failed."
        ),
    )
    p.add_argument(
        "--include-equipment-opportunities",
        action="store_true",
        help="After mirror loaders, run equipment_first_operator_queue Postgres mirror (DB-2A).",
    )
    p.add_argument(
        "--include-warm-cases",
        action="store_true",
        help="After mirror loaders, promote SQLite warm review queue to Postgres (DB-2B).",
    )
    p.add_argument(
        "--updated-by",
        "--operator",
        dest="updated_by",
        default=None,
        help="Operator id for optional DB-2 loaders (required with --apply when flags set).",
    )
    p.add_argument(
        "--reason",
        default=None,
        help="Audit reason for optional DB-2 loaders (required with --apply when flags set).",
    )
    return p


def run_dashboard_mirror_sync(
    argv: list[str] | None = None,
    *,
    repo_root: Path | None = None,
    loader_runner: Callable[[list[str], Path], int] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    root = repo_root or Path(__file__).resolve().parents[2]
    run_loader = loader_runner or run_loader_subprocess

    result: dict[str, Any] = {
        "ok": False,
        "dry_run": bool(args.dry_run),
        "status": "failed",
        "sqlite_path": "",
        "postgres_url_redacted": "",
        "alembic_version": None,
        "loader_steps": [],
        "counts": {},
        "sync_run_id": None,
        "errors": [],
        "warnings": [],
        "elapsed_seconds": 0.0,
    }

    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)

    try:
        sqlite_path = resolve_sqlite_path(args.sqlite_db)
        pg_url = resolve_postgres_url(args.postgres_url)
        assert_scratch_postgres_target(
            pg_url, allow_non_scratch=bool(args.allow_non_scratch_postgres)
        )
        validate_optional_loader_audit(
            include_equipment=bool(args.include_equipment_opportunities),
            include_warm_cases=bool(args.include_warm_cases),
            dry_run=bool(args.dry_run),
            updated_by=args.updated_by,
            reason=args.reason,
        )
    except (ValueError, RuntimeError) as exc:
        result["errors"].append(str(exc))
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    result["sqlite_path"] = str(sqlite_path)
    result["postgres_url_redacted"] = redact_postgres_url(pg_url)

    phase_log("[sync] preflight SQLite (read-only)...", log=log)
    try:
        preflight_sqlite(sqlite_path)
    except (FileNotFoundError, sqlite3.Error) as exc:
        result["errors"].append(str(exc))
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    phase_log("[sync] preflight Postgres...", log=log)
    try:
        alembic_version, reporting_missing = preflight_postgres(pg_url)
        result["alembic_version"] = alembic_version
        if reporting_missing:
            result["warnings"].append(
                "reporting.dashboard_sync_run not present; watermark row skipped "
                "(run alembic upgrade head)."
            )
    except ValueError as exc:
        result["errors"].append(str(exc))
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    try:
        steps = plan_loader_steps(
            only=args.only,
            skip_outbound=bool(args.skip_outbound),
            skip_mart=bool(args.skip_mart),
        )
    except ValueError as exc:
        result["errors"].append(str(exc))
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    result["loader_steps"] = [
        {"name": s.name, "script": s.script_relpath, "argv": list(s.argv)} for s in steps
    ]

    if mart_loader_planned(steps):
        phase_log("[sync] checking SQLite mart source counts (read-only)...", log=log)
        try:
            source_counts = assert_sqlite_mart_ready_for_mirror_sync(
                sqlite_path,
                allow_empty_mart=bool(args.allow_empty_mart),
            )
            result["sqlite_source_counts"] = {
                "canonical_gmail_email_count": source_counts.canonical_gmail_email_count,
                **source_counts.mart_table_counts,
            }
        except ValueError as exc:
            result["errors"].append(str(exc))
            result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
            return result

    if args.dry_run:
        result["counts"] = collect_mirror_counts(pg_url)
        equipment_summary: dict[str, Any] | None = None
        warm_summary: dict[str, Any] | None = None
        if args.include_equipment_opportunities or args.include_warm_cases:
            try:
                equipment_summary, warm_summary = run_optional_db2_loaders(
                    args=args,
                    pg_url=pg_url,
                    sqlite_path=sqlite_path,
                    repo_root=root,
                    sync_run_id=None,
                    dry_run=True,
                )
            except RuntimeError as exc:
                result["errors"].append(str(exc))
                result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
                return result
        if equipment_summary is not None:
            result["equipment_opportunity_sync"] = equipment_summary
        if warm_summary is not None:
            result["warm_case_sync"] = warm_summary
        result["details"] = merge_optional_loader_details(
            {"loader_steps": result["loader_steps"], "alembic_version": alembic_version},
            equipment_summary=equipment_summary,
            warm_summary=warm_summary,
        )
        result["ok"] = True
        result["status"] = "dry_run"
        result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
        phase_log("[sync] dry-run ok (no loaders executed, Postgres mirror unchanged)", log=log)
        return result

    error_message: str | None = None
    try:
        for step in steps:
            cmd = build_loader_command(
                root,
                step,
                sqlite_path=sqlite_path,
                postgres_url=pg_url,
                allow_non_scratch=bool(args.allow_non_scratch_postgres),
            )
            phase_log(f"[sync] loader {step.name}: {' '.join(cmd[2:6])} ...", log=log)
            if loader_runner is not None:
                rc = loader_runner(cmd, root)
            else:
                rc = run_loader_subprocess(cmd, repo_root=root)
            if rc != 0:
                raise RuntimeError(f"Loader {step.name} failed with exit code {rc}")

        result["counts"] = collect_mirror_counts(pg_url)
        finished_at = datetime.now(timezone.utc)
        sync_id = write_sync_watermark(
            pg_url,
            sqlite_path=sqlite_path,
            postgres_url_redacted=result["postgres_url_redacted"],
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            counts=result["counts"],
            error_message=None,
            details={"loader_steps": result["loader_steps"], "alembic_version": alembic_version},
            dry_run=False,
        )
        result["sync_run_id"] = sync_id
        classification_sync = sync_email_classification_canonical(
            pg_url,
            sqlite_path,
            sync_run_id=sync_id,
            dry_run=False,
        )
        result["classification_sync"] = classification_sync
        purchase_sync = sync_commercial_purchase_events(
            pg_url,
            sqlite_path,
            sync_run_id=sync_id,
            dry_run=False,
        )
        result["commercial_purchase_sync"] = purchase_sync

        details: dict[str, Any] = {
            "loader_steps": result["loader_steps"],
            "alembic_version": alembic_version,
            "classification_sync": classification_sync,
            "commercial_purchase_sync": purchase_sync,
        }
        equipment_summary: dict[str, Any] | None = None
        warm_summary: dict[str, Any] | None = None
        if args.include_equipment_opportunities or args.include_warm_cases:
            equipment_summary, warm_summary = run_optional_db2_loaders(
                args=args,
                pg_url=pg_url,
                sqlite_path=sqlite_path,
                repo_root=root,
                sync_run_id=sync_id,
                dry_run=False,
            )
            if equipment_summary is not None:
                result["equipment_opportunity_sync"] = equipment_summary
            if warm_summary is not None:
                result["warm_case_sync"] = warm_summary
            details = merge_optional_loader_details(
                details,
                equipment_summary=equipment_summary,
                warm_summary=warm_summary,
            )
            if sync_id is not None:
                update_sync_run_details(pg_url, sync_id, details)

        result["details"] = details
        result["counts"] = collect_mirror_counts(pg_url)
        result["ok"] = True
        result["status"] = "success"
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)
        result["errors"].append(error_message)
        result["status"] = "failed"
        try:
            result["counts"] = collect_mirror_counts(pg_url)
        except Exception:  # noqa: BLE001
            pass
        write_sync_watermark(
            pg_url,
            sqlite_path=sqlite_path,
            postgres_url_redacted=result["postgres_url_redacted"],
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            counts=result.get("counts") or {},
            error_message=error_message,
            details={"loader_steps": result["loader_steps"]},
            dry_run=False,
        )

    result["elapsed_seconds"] = round(time.monotonic() - t0, 3)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_dashboard_mirror_sync(
        argv,
        loader_runner=None,
    )
    if args.json_out:
        args.json_out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    print(format_summary_text(result))
    if result.get("errors"):
        for err in result["errors"]:
            print(err, file=sys.stderr)
    return 0 if result.get("ok") else 1
