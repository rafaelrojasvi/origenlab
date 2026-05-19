"""Read-only operator status report (SQLite, active/current, manifest)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.outbound_core import resolve_outbound_gmail_user, resolve_outbound_sent_folders
from origenlab_email_pipeline.outbound_readiness_check import assess_outbound_readiness


@dataclass
class OperatorStatusReport:
    """Structured operator status (read-only)."""

    verdict: str  # READY | CAUTION | BLOCKED
    generated_at: str
    sqlite_path: str
    sqlite_exists: bool
    sqlite_size_bytes: int | None
    emails_global_max_date_iso: str | None
    emails_2026_max_date_iso: str | None
    sent: dict[str, Any] = field(default_factory=dict)
    auxiliary_files: dict[str, Any] = field(default_factory=dict)
    canonical_files: dict[str, Any] = field(default_factory=dict)
    equipment_queue: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    postgres: dict[str, Any] = field(default_factory=dict)
    api: dict[str, Any] = field(default_factory=dict)
    outbound_readiness: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_json_obj(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_freshness(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    st = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": st.st_size,
        "mtime_iso": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


def _count_csv_rows(path: Path) -> int | None:
    if not path.is_file():
        return None
    import csv

    with path.open(newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def _latest_equipment_operator_queue(active_current: Path) -> Path | None:
    candidates = sorted(active_current.glob("equipment_first_operator_queue_*.csv"))
    return candidates[-1] if candidates else None


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": True}


def probe_postgres_status() -> dict[str, Any]:
    """Classify Postgres URL presence and optional read-only ping."""
    import os

    url = (
        (os.environ.get("ORIGENLAB_POSTGRES_URL") or "").strip()
        or (os.environ.get("ALEMBIC_DATABASE_URL") or "").strip()
    )
    out: dict[str, Any] = {
        "status": "parked",
        "url_configured": bool(url),
        "detail": "Postgres is optional; daily outbound uses SQLite only.",
    }
    if not url:
        return out
    lower = url.lower()
    if "scratch" in lower or "127.0.0.1" in lower or "localhost" in lower:
        out["classification"] = "scratch_or_local"
    else:
        out["classification"] = "non_scratch_url_configured"
        out["warnings"] = ["Postgres URL set — do not run migrate --replace without explicit approval."]
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        out["reachable"] = True
        out["status"] = "available"
        out["detail"] = "Read-only SELECT 1 succeeded (no writes performed)."
    except Exception as exc:  # noqa: BLE001 — operator diagnostic
        out["reachable"] = False
        out["status"] = "parked"
        out["detail"] = f"URL configured but not reachable: {type(exc).__name__}"
    return out


def compute_verdict(
    *,
    sqlite_exists: bool,
    readiness_verdict: str,
    manifest_warnings: list[str],
    extra_errors: list[str],
) -> str:
    if extra_errors or not sqlite_exists:
        return "BLOCKED"
    if readiness_verdict == "not_ready":
        return "BLOCKED"
    if readiness_verdict in ("ready_with_warnings",) or manifest_warnings:
        return "CAUTION"
    return "READY"


def build_operator_status_report(
    *,
    sqlite_path: Path,
    active_current: Path,
    manifest_path: Path,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    max_staleness_days: float = 14.0,
) -> OperatorStatusReport:
    generated_at = _utc_now_iso()
    errors: list[str] = []
    warnings: list[str] = []

    manifest = load_manifest(manifest_path)
    if manifest.get("_parse_error"):
        errors.append(f"manifest.json parse error: {manifest_path}")
        manifest = {}
    manifest_warnings = list(manifest.get("known_warnings") or [])

    sqlite_exists = sqlite_path.is_file()
    size_bytes: int | None = None
    global_max: str | None = None
    max_2026: str | None = None
    sent_info: dict[str, Any] = {}

    if sqlite_exists:
        size_bytes = sqlite_path.stat().st_size
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT MAX(date_iso) FROM emails").fetchone()
            global_max = row[0] if row else None
            row2 = conn.execute(
                "SELECT MAX(date_iso) FROM emails WHERE date_iso >= '2026-01-01' AND date_iso < '2027-01-01'"
            ).fetchone()
            max_2026 = row2[0] if row2 else None
            if global_max and str(global_max)[:4] not in ("2024", "2025", "2026"):
                warnings.append(
                    f"Global MAX(date_iso) outlier ({global_max}) — prefer 2026-filtered freshness."
                )

            pred = sql_predicate_contacto_gmail_source()
            sent_row = conn.execute(
                f"""
                SELECT COUNT(*), MAX(date_iso) FROM emails
                WHERE {pred}
                  AND (
                    source_file LIKE '%Enviados%'
                    OR source_file LIKE '%Sent%'
                  )
                """,
            ).fetchone()
            sent_info = {
                "gmail_user": gmail_user,
                "sent_folders_config": list(sent_folders),
                "canonical_sent_row_count": int(sent_row[0] or 0) if sent_row else 0,
                "canonical_sent_max_date_iso": sent_row[1] if sent_row else None,
            }

            try:
                readiness = assess_outbound_readiness(
                    conn,
                    sqlite_path=sqlite_path,
                    sqlite_exists=True,
                    gmail_user=gmail_user,
                    sent_folders=sent_folders,
                    max_staleness_days=max_staleness_days,
                    strict_commercial_required=False,
                )
                readiness_obj = readiness.to_json_obj()
                warnings.extend(readiness.warnings)
                errors.extend(readiness.errors)
            except sqlite3.OperationalError as exc:
                readiness_obj = {
                    "verdict": "not_ready",
                    "skipped": True,
                    "error": str(exc),
                }
                warnings.append(f"outbound_readiness skipped (schema): {exc}")
        finally:
            conn.close()
    else:
        errors.append(f"SQLite not found: {sqlite_path}")
        readiness_obj = assess_outbound_readiness(
            sqlite3.connect(":memory:"),
            sqlite_path=sqlite_path,
            sqlite_exists=False,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            max_staleness_days=max_staleness_days,
            strict_commercial_required=False,
        ).to_json_obj()

    aux_names = (
        "do_not_repeat_master.csv",
        "outreach_contacted_all.csv",
        "all_known_marketing_contacts_dedup.csv",
    )
    auxiliary: dict[str, Any] = {}
    for name in aux_names:
        for base in (active_current, active_current.parent):
            auxiliary[name] = _file_freshness(base / name)

    canonical_from_manifest = list(manifest.get("canonical_files") or [])
    canonical: dict[str, Any] = {}
    for rel in canonical_from_manifest:
        p = active_current / rel if not str(rel).startswith("/") else Path(rel)
        canonical[rel] = _file_freshness(p)

    equip_path = _latest_equipment_operator_queue(active_current)
    equipment: dict[str, Any] = {"path": str(equip_path) if equip_path else None, "row_count": None}
    if equip_path:
        equipment["row_count"] = _count_csv_rows(equip_path)
        equipment.update(_file_freshness(equip_path))

    for w in manifest_warnings:
        if w not in warnings:
            warnings.append(w)

    verdict = compute_verdict(
        sqlite_exists=sqlite_exists,
        readiness_verdict=str(readiness_obj.get("verdict", "not_ready")),
        manifest_warnings=manifest_warnings,
        extra_errors=errors,
    )

    return OperatorStatusReport(
        verdict=verdict,
        generated_at=generated_at,
        sqlite_path=str(sqlite_path),
        sqlite_exists=sqlite_exists,
        sqlite_size_bytes=size_bytes,
        emails_global_max_date_iso=global_max,
        emails_2026_max_date_iso=max_2026,
        sent=sent_info,
        auxiliary_files=auxiliary,
        canonical_files=canonical,
        equipment_queue=equipment,
        manifest={"path": str(manifest_path), "loaded": bool(manifest), "keys": sorted(manifest.keys())},
        postgres=probe_postgres_status(),
        api={
            "status": "parked",
            "detail": "FastAPI/React dashboard is optional; not required for DNR or equipment-first ops.",
        },
        outbound_readiness=readiness_obj,
        warnings=warnings,
        errors=errors,
    )


def format_human_report(report: OperatorStatusReport) -> str:
    lines = [
        f"Operator status — verdict: {report.verdict}",
        f"Generated: {report.generated_at}",
        "",
        f"SQLite: {report.sqlite_path}",
        f"  exists: {report.sqlite_exists}",
    ]
    if report.sqlite_size_bytes is not None:
        lines.append(f"  size_bytes: {report.sqlite_size_bytes:,}")
    lines.extend(
        [
            f"  emails MAX(date_iso) global: {report.emails_global_max_date_iso}",
            f"  emails MAX(date_iso) 2026: {report.emails_2026_max_date_iso}",
            "",
            "Gmail Sent (canonical):",
        ]
    )
    for k, v in report.sent.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Equipment-first operator queue:")
    for k, v in report.equipment_queue.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Auxiliary anti-repeat files:")
    for name, meta in report.auxiliary_files.items():
        lines.append(f"  {name}: exists={meta.get('exists')} mtime={meta.get('mtime_iso', 'n/a')}")
    lines.append("")
    lines.append(f"Postgres: {report.postgres.get('status')} — {report.postgres.get('detail')}")
    lines.append(f"API: {report.api.get('status')} — {report.api.get('detail')}")
    lines.append(f"Outbound readiness: {report.outbound_readiness.get('verdict', 'n/a')}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in report.warnings:
            lines.append(f"  - {w}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for e in report.errors:
            lines.append(f"  - {e}")
    return "\n".join(lines)
