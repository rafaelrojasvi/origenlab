"""Dry-run planning for safe NDR auto-apply (Batch A only in initial rollout)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.qa.ndr_pending_review_status import (
    NDR_REVIEW_SUMMARY_FILENAME,
    find_latest_ndr_review_queue_dir,
    load_ndr_review_summary_json,
)
from origenlab_email_pipeline.qa.ndr_review_queue import (
    APPLY_ONLY_CODE_BATCH_A,
    BatchName,
)

SUPPORTED_DRY_RUN_BATCHES: frozenset[BatchName] = frozenset({"A"})
ALLOWLIST_BATCH_A_FILENAME = "apply_allowlist_batch_a.txt"
NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME = "ndr_safe_auto_apply_audit.jsonl"

ExitCode = Literal[0, 1, 2]
NowFn = Callable[[], datetime]


@dataclass(frozen=True)
class NdrSafeAutoApplyOptions:
    batch: BatchName
    dry_run: bool = True
    json_output: bool = False
    queue_dir: Path | None = None
    reports_dir: Path | None = None
    operator: str | None = None


def _iso_now(now_fn: NowFn | None = None) -> str:
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def ndr_safe_auto_apply_audit_path(active_current: Path) -> Path:
    return active_current / NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME


def build_ndr_safe_auto_apply_audit_record(
    plan: dict[str, Any],
    *,
    operator: str | None,
    timestamp_utc: str,
) -> dict[str, Any]:
    emails = plan.get("emails")
    if not isinstance(emails, list):
        emails = []
    allowlist_count = plan.get("allowlist_count")
    if allowlist_count is None and emails:
        allowlist_count = len(emails)
    return {
        "timestamp_utc": timestamp_utc,
        "dry_run": True,
        "batch": plan.get("batch"),
        "reason": plan.get("reason"),
        "queue_dir": plan.get("queue_dir"),
        "queue_generated_at_utc": plan.get("generated_at_utc"),
        "candidates_total": plan.get("candidates_total"),
        "candidates_already_suppressed": plan.get("candidates_already_suppressed"),
        "candidates_unsuppressed": plan.get("candidates_unsuppressed"),
        "allowlist_count": allowlist_count,
        "emails": emails,
        "only_code": plan.get("only_code"),
        "applied": False,
        "operator": operator,
    }


def append_ndr_safe_auto_apply_audit_record(
    active_current: Path,
    record: dict[str, Any],
) -> Path:
    """Append one JSONL audit line under active/current (dry-run evidence only)."""
    active_current.mkdir(parents=True, exist_ok=True)
    audit_path = ndr_safe_auto_apply_audit_path(active_current)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return audit_path


def _active_current_path(reports_dir: Path | None = None) -> Path:
    base = reports_dir or load_settings().resolved_reports_dir()
    return base / "active" / "current"


def load_ndr_allowlist_emails(path: Path) -> list[str]:
    """Load one email per line; ignore blanks and ``#`` comments."""
    emails: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        emails.append(line.lower())
    return emails


def resolve_ndr_review_queue_dir(
    *,
    active_current: Path,
    queue_dir: Path | None,
) -> Path | None:
    if queue_dir is not None:
        return queue_dir if queue_dir.is_dir() else None
    return find_latest_ndr_review_queue_dir(active_current)


def build_ndr_safe_auto_apply_plan(
    options: NdrSafeAutoApplyOptions,
) -> tuple[dict[str, Any], ExitCode]:
    """Build a dry-run apply plan from on-disk ndr_review_queue artifacts."""
    if options.batch not in SUPPORTED_DRY_RUN_BATCHES:
        return (
            {
                "dry_run": True,
                "batch": options.batch,
                "reason": "unsupported_batch",
                "message": (
                    f"Batch {options.batch} is not enabled for ndr-safe-auto-apply yet "
                    "(Batch A dry-run only)."
                ),
            },
            1,
        )

    active_current = _active_current_path(options.reports_dir)
    queue_dir = resolve_ndr_review_queue_dir(
        active_current=active_current,
        queue_dir=options.queue_dir,
    )
    if queue_dir is None:
        return (
            {
                "dry_run": True,
                "batch": options.batch,
                "reason": "missing_queue",
                "message": "No ndr_review_queue_* directory found. Run: uv run origenlab ndr-review",
                "queue_dir": None,
            },
            2,
        )

    summary, parse_error = load_ndr_review_summary_json(queue_dir)
    if summary is None:
        return (
            {
                "dry_run": True,
                "batch": options.batch,
                "reason": parse_error or "malformed_summary",
                "message": f"Could not read {NDR_REVIEW_SUMMARY_FILENAME} under {queue_dir}",
                "queue_dir": str(queue_dir.resolve()),
            },
            2,
        )

    allowlist_path = queue_dir / ALLOWLIST_BATCH_A_FILENAME
    if not allowlist_path.is_file():
        return (
            {
                "dry_run": True,
                "batch": options.batch,
                "reason": "missing_allowlist",
                "message": f"Missing {ALLOWLIST_BATCH_A_FILENAME} in queue directory",
                "queue_dir": str(queue_dir.resolve()),
                "generated_at_utc": summary.get("generated_at"),
            },
            2,
        )

    emails = load_ndr_allowlist_emails(allowlist_path)
    reason = "ready" if emails else "no_candidates"

    plan: dict[str, Any] = {
        "dry_run": True,
        "batch": options.batch,
        "only_code": APPLY_ONLY_CODE_BATCH_A,
        "reason": reason,
        "queue_dir": str(queue_dir.resolve()),
        "generated_at_utc": summary.get("generated_at"),
        "since_days": summary.get("since_days"),
        "date_label": summary.get("date_label"),
        "candidates_total": summary.get("candidates_total"),
        "candidates_already_suppressed": summary.get("candidates_already_suppressed"),
        "candidates_unsuppressed": summary.get("candidates_unsuppressed"),
        "allowlist_count": len(emails),
        "emails": emails,
    }
    return plan, 0


def format_ndr_safe_auto_apply_text(plan: dict[str, Any]) -> str:
    lines = [
        "ndr_safe_auto_apply",
        f"dry_run={plan.get('dry_run', True)}",
        f"batch={plan.get('batch', '')}",
        f"reason={plan.get('reason', '')}",
    ]
    if plan.get("message"):
        lines.append(f"message={plan['message']}")
    for key in (
        "only_code",
        "queue_dir",
        "generated_at_utc",
        "since_days",
        "date_label",
        "candidates_total",
        "candidates_already_suppressed",
        "candidates_unsuppressed",
        "allowlist_count",
    ):
        if key in plan and plan[key] is not None:
            lines.append(f"{key}={plan[key]}")
    emails = plan.get("emails")
    if isinstance(emails, list) and emails:
        lines.append("emails:")
        for email in emails:
            lines.append(f"  - {email}")
    return "\n".join(lines) + "\n"


def run_ndr_safe_auto_apply(
    options: NdrSafeAutoApplyOptions,
    *,
    now_fn: NowFn | None = None,
) -> int:
    if not options.dry_run:
        print(
            "ndr-safe-auto-apply: --apply is not implemented yet (dry-run only).",
            file=sys.stderr,
        )
        return 1

    plan, exit_code = build_ndr_safe_auto_apply_plan(options)
    active_current = _active_current_path(options.reports_dir)
    audit_record = build_ndr_safe_auto_apply_audit_record(
        plan,
        operator=options.operator,
        timestamp_utc=_iso_now(now_fn),
    )
    append_ndr_safe_auto_apply_audit_record(active_current, audit_record)
    plan["audit_path"] = str(ndr_safe_auto_apply_audit_path(active_current).resolve())

    if options.json_output:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(format_ndr_safe_auto_apply_text(plan), end="")
    return int(exit_code)


def parse_ndr_safe_auto_apply_args(argv: list[str]) -> NdrSafeAutoApplyOptions:
    parser = argparse.ArgumentParser(prog="ndr-safe-auto-apply", add_help=True)
    parser.add_argument(
        "--batch",
        required=True,
        choices=["A", "B", "C", "D", "E"],
        help="Human-review batch to plan (Batch A dry-run only in this release)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview allowlist and metadata without writing suppressions (default mode)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Not implemented yet — refused in this release",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    parser.add_argument(
        "--queue-dir",
        type=Path,
        default=None,
        help="Use a specific ndr_review_queue_* directory instead of the latest",
    )
    parser.add_argument(
        "--operator",
        default=None,
        help="Operator name recorded in dry-run audit JSONL (optional)",
    )
    ns = parser.parse_args(argv)
    if ns.apply:
        parser.error("--apply is not implemented yet; use --dry-run only")
    operator = (ns.operator or "").strip() or None
    return NdrSafeAutoApplyOptions(
        batch=ns.batch,
        dry_run=True,
        json_output=ns.json,
        queue_dir=ns.queue_dir,
        operator=operator,
    )


def print_ndr_safe_auto_apply_help() -> None:
    print(
        "ndr-safe-auto-apply — dry-run plan for safe NDR Batch A suppressions\n\n"
        "  uv run origenlab ndr-safe-auto-apply --batch A --dry-run\n"
        "  uv run origenlab ndr-safe-auto-apply --batch A --dry-run --json\n"
        "  uv run origenlab ndr-safe-auto-apply --batch A --dry-run --operator rafael\n"
        "  uv run origenlab ndr-safe-auto-apply --batch A --queue-dir reports/out/active/current/ndr_review_queue_2026_06_11\n\n"
        "Reads the latest ndr_review_queue artifact (or --queue-dir). Appends dry-run evidence to "
        f"active/current/{NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME}. No SQLite writes, "
        "no refresh-safety, no --apply in this release.\n"
    )
