"""Daily-core apply run manifest (operator visibility only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.core.step_runner import StepResult
from origenlab_email_pipeline.operator_cli.constants import DAILY_CORE_USAGE, REFRESH_DASHBOARD_USAGE

MANIFEST_FILENAME = "daily_core_run_manifest.json"
SCHEMA_VERSION = 1
WORKFLOW = "daily-core"
OPERATIONAL_TRUTH = "SQLite + Gmail Sent history inside SQLite"
POSTGRES_MIRROR = "not included"

SAFETY: dict[str, bool] = {
    "sends_email": False,
    "purges_data": False,
    "applies_ndr_suppressions": False,
    "runs_alembic": False,
    "runs_postgres_mirror": False,
}


def daily_core_run_manifest_path(reports_dir: Path | None = None) -> Path:
    base = reports_dir or load_settings().resolved_reports_dir()
    return base / "active" / "current" / MANIFEST_FILENAME


def format_daily_core_command(
    *,
    skip_ingest: bool = False,
    since_days: int | None = None,
) -> str:
    parts = [DAILY_CORE_USAGE, "--apply"]
    if skip_ingest:
        parts.append("--skip-ingest")
    if since_days is not None:
        parts.extend(["--since-days", str(since_days)])
    return " ".join(parts)


def format_equivalent_refresh_command(
    *,
    skip_ingest: bool = False,
    since_days: int | None = None,
) -> str:
    parts = [REFRESH_DASHBOARD_USAGE, "--apply", "--no-mirror"]
    if skip_ingest:
        parts.append("--skip-ingest")
    if since_days is not None:
        parts.extend(["--since-days", str(since_days)])
    return " ".join(parts)


def build_daily_core_run_manifest_payload(
    *,
    step_results: list[StepResult],
    returncode: int,
    skip_ingest: bool = False,
    since_days: int | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    ts = generated_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW,
        "generated_at_utc": ts,
        "command": format_daily_core_command(skip_ingest=skip_ingest, since_days=since_days),
        "equivalent_command": format_equivalent_refresh_command(
            skip_ingest=skip_ingest,
            since_days=since_days,
        ),
        "operational_truth": OPERATIONAL_TRUTH,
        "postgres_mirror": POSTGRES_MIRROR,
        "send_approval": False,
        "safety": dict(SAFETY),
        "steps": [{"label": result.label, "returncode": result.returncode} for result in step_results],
        "status": "success" if returncode == 0 else "failed",
        "returncode": returncode,
    }


def write_daily_core_run_manifest(
    *,
    step_results: list[StepResult],
    returncode: int,
    skip_ingest: bool = False,
    since_days: int | None = None,
    manifest_path: Path | None = None,
) -> Path:
    path = manifest_path or daily_core_run_manifest_path()
    payload = build_daily_core_run_manifest_payload(
        step_results=step_results,
        returncode=returncode,
        skip_ingest=skip_ingest,
        since_days=since_days,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summarize_daily_core_run_manifest(path: Path) -> tuple[dict[str, Any], str | None]:
    """Read-only summary for operator status. Returns ``(summary, warning_or_none)``."""
    summary: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return summary, None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            **summary,
            "loaded": False,
            "parse_error": True,
        }, f"daily_core_run_manifest.json parse error: {path}"

    steps = data.get("steps") or []
    last_step = steps[-1].get("label") if steps else None
    return {
        **summary,
        "loaded": True,
        "schema_version": data.get("schema_version"),
        "workflow": data.get("workflow"),
        "generated_at_utc": data.get("generated_at_utc"),
        "status": data.get("status"),
        "returncode": data.get("returncode"),
        "step_count": len(steps),
        "last_step": last_step,
        "send_approval": data.get("send_approval"),
        "postgres_mirror": data.get("postgres_mirror"),
    }, None
