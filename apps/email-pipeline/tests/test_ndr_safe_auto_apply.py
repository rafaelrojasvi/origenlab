"""Tests for dry-run ndr-safe-auto-apply command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from origenlab_email_pipeline.operator_cli.ndr_safe_auto_apply import (
    ALLOWLIST_BATCH_A_FILENAME,
    NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME,
    NdrSafeAutoApplyOptions,
    build_ndr_safe_auto_apply_plan,
    run_ndr_safe_auto_apply,
)
from origenlab_email_pipeline.operator_cli.parser import main
from origenlab_email_pipeline.qa.ndr_review_queue import APPLY_ONLY_CODE_BATCH_A


def _write_queue(
    active_current: Path,
    *,
    date_label: str,
    summary: dict[str, object],
    allowlist_emails: list[str] | None = None,
    include_allowlist: bool = True,
) -> Path:
    queue_dir = active_current / f"ndr_review_queue_{date_label}"
    queue_dir.mkdir(parents=True)
    (queue_dir / "ndr_review_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    if include_allowlist:
        lines = [
            "# SUGGESTED allowlist only — DO NOT APPLY WITHOUT OPERATOR APPROVAL",
            f"# Use with: --emails-file <this-file> --only-code {APPLY_ONLY_CODE_BATCH_A} --apply",
            "",
        ]
        for email in allowlist_emails or []:
            lines.append(email)
        (queue_dir / ALLOWLIST_BATCH_A_FILENAME).write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return queue_dir


_FIXED_NOW = datetime(2026, 6, 11, 22, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    active_current = tmp_path / "active" / "current"
    active_current.mkdir(parents=True)
    return tmp_path


def _read_audit_lines(active_current: Path) -> list[dict[str, object]]:
    audit_path = active_current / NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME
    if not audit_path.is_file():
        return []
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _run_with_reports(
    reports_dir: Path,
    options: NdrSafeAutoApplyOptions,
    *,
    capsys: pytest.CaptureFixture[str] | None = None,
) -> int:
    with patch(
        "origenlab_email_pipeline.operator_cli.ndr_safe_auto_apply.load_settings"
    ) as mock_settings:
        mock_settings.return_value.resolved_reports_dir.return_value = reports_dir
        return run_ndr_safe_auto_apply(
            options,
            now_fn=lambda: _FIXED_NOW,
        )


def test_batch_a_dry_run_lists_candidates(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    queue_dir = _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "since_days": 1,
            "date_label": "2026_06_11",
            "candidates_total": 129,
            "candidates_already_suppressed": 53,
            "candidates_unsuppressed": 76,
            "batch_counts": {"A": 53, "B": 28, "C": 1, "D": 42, "E": 5},
            "allowlist_batch_a_count": 2,
            "allowlist_batch_b_count": 14,
        },
        allowlist_emails=["alpha@example.cl", "beta@example.cl"],
    )
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch="A", queue_dir=queue_dir, reports_dir=reports_dir),
    )
    assert exit_code == 0
    assert plan["reason"] == "ready"
    assert plan["only_code"] == APPLY_ONLY_CODE_BATCH_A
    assert plan["allowlist_count"] == 2
    assert plan["emails"] == ["alpha@example.cl", "beta@example.cl"]
    assert plan["candidates_total"] == 129
    assert plan["candidates_already_suppressed"] == 53
    assert plan["candidates_unsuppressed"] == 76
    assert plan["queue_dir"] == str(queue_dir.resolve())


def test_empty_batch_a_returns_no_op_success(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "candidates_total": 5,
            "candidates_already_suppressed": 5,
            "candidates_unsuppressed": 0,
            "batch_counts": {"A": 5, "B": 0, "C": 0, "D": 0, "E": 0},
            "allowlist_batch_a_count": 0,
        },
        allowlist_emails=[],
    )
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch="A", reports_dir=reports_dir),
    )
    assert exit_code == 0
    assert plan["reason"] == "no_candidates"
    assert plan["allowlist_count"] == 0
    assert plan["emails"] == []


@pytest.mark.parametrize("batch", ["B", "C", "D", "E"])
def test_unsupported_batches_refused(reports_dir: Path, batch: str) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={"generated_at": "2026-06-11T21:43:08+00:00", "candidates_total": 1},
        allowlist_emails=["x@example.cl"],
    )
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch=batch, reports_dir=reports_dir),  # type: ignore[arg-type]
    )
    assert exit_code == 1
    assert plan["reason"] == "unsupported_batch"


def test_missing_queue_dir_returns_error(reports_dir: Path) -> None:
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch="A", reports_dir=reports_dir),
    )
    assert exit_code == 2
    assert plan["reason"] == "missing_queue"


def test_missing_summary_returns_error(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    queue_dir = active_current / "ndr_review_queue_2026_06_11"
    queue_dir.mkdir(parents=True)
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch="A", queue_dir=queue_dir, reports_dir=reports_dir),
    )
    assert exit_code == 2
    assert plan["reason"] == "missing_summary"


def test_missing_allowlist_returns_error(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    queue_dir = _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={"generated_at": "2026-06-11T21:43:08+00:00", "candidates_total": 1},
        include_allowlist=False,
    )
    plan, exit_code = build_ndr_safe_auto_apply_plan(
        NdrSafeAutoApplyOptions(batch="A", queue_dir=queue_dir, reports_dir=reports_dir),
    )
    assert exit_code == 2
    assert plan["reason"] == "missing_allowlist"


def test_dry_run_writes_audit_record(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    queue_dir = _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "candidates_total": 2,
            "candidates_already_suppressed": 0,
            "candidates_unsuppressed": 2,
        },
        allowlist_emails=["audit@example.cl"],
    )
    rc = _run_with_reports(
        reports_dir,
        NdrSafeAutoApplyOptions(
            batch="A",
            operator="rafael",
            reports_dir=reports_dir,
        ),
    )
    assert rc == 0
    records = _read_audit_lines(active_current)
    assert len(records) == 1
    record = records[0]
    assert record["timestamp_utc"] == "2026-06-11T22:00:00+00:00"
    assert record["dry_run"] is True
    assert record["applied"] is False
    assert record["batch"] == "A"
    assert record["reason"] == "ready"
    assert record["operator"] == "rafael"
    assert record["only_code"] == APPLY_ONLY_CODE_BATCH_A
    assert record["emails"] == ["audit@example.cl"]
    assert record["queue_dir"] == str(queue_dir.resolve())
    assert record["queue_generated_at_utc"] == "2026-06-11T21:43:08+00:00"


def test_no_candidates_dry_run_writes_audit_record(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "candidates_total": 3,
            "candidates_already_suppressed": 3,
            "candidates_unsuppressed": 0,
        },
        allowlist_emails=[],
    )
    rc = _run_with_reports(
        reports_dir,
        NdrSafeAutoApplyOptions(batch="A", reports_dir=reports_dir),
    )
    assert rc == 0
    record = _read_audit_lines(active_current)[0]
    assert record["reason"] == "no_candidates"
    assert record["dry_run"] is True
    assert record["applied"] is False
    assert record["allowlist_count"] == 0
    assert record["emails"] == []
    assert record["operator"] is None


def test_unsupported_batch_writes_refused_audit(reports_dir: Path) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={"generated_at": "2026-06-11T21:43:08+00:00", "candidates_total": 1},
        allowlist_emails=["x@example.cl"],
    )
    rc = _run_with_reports(
        reports_dir,
        NdrSafeAutoApplyOptions(batch="B", reports_dir=reports_dir),
    )
    assert rc == 1
    record = _read_audit_lines(active_current)[0]
    assert record["reason"] == "unsupported_batch"
    assert record["dry_run"] is True
    assert record["applied"] is False
    assert record["batch"] == "B"
    assert record["only_code"] is None
    assert record["emails"] == []


@patch("origenlab_email_pipeline.contact_email_suppression.upsert_contact_email_suppression")
@patch("subprocess.run")
def test_dry_run_does_not_write_or_run_refresh_safety(
    mock_run: object,
    mock_upsert: object,
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "candidates_total": 1,
            "candidates_already_suppressed": 0,
            "candidates_unsuppressed": 1,
        },
        allowlist_emails=["safe@example.cl"],
    )
    with patch(
        "origenlab_email_pipeline.operator_cli.ndr_safe_auto_apply.load_settings"
    ) as mock_settings:
        mock_settings.return_value.resolved_reports_dir.return_value = reports_dir
        rc = run_ndr_safe_auto_apply(
            NdrSafeAutoApplyOptions(batch="A", json_output=True, reports_dir=reports_dir),
            now_fn=lambda: _FIXED_NOW,
        )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["emails"] == ["safe@example.cl"]
    assert data["audit_path"].endswith(NDR_SAFE_AUTO_APPLY_AUDIT_FILENAME)
    mock_upsert.assert_not_called()
    mock_run.assert_not_called()
    record = _read_audit_lines(active_current)[0]
    assert record["dry_run"] is True
    assert record["applied"] is False


def test_cli_batch_a_dry_run_integration(reports_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    active_current = reports_dir / "active" / "current"
    _write_queue(
        active_current,
        date_label="2026_06_11",
        summary={
            "generated_at": "2026-06-11T21:43:08+00:00",
            "candidates_total": 2,
            "candidates_already_suppressed": 0,
            "candidates_unsuppressed": 2,
        },
        allowlist_emails=["cli@example.cl"],
    )
    with patch(
        "origenlab_email_pipeline.operator_cli.ndr_safe_auto_apply.load_settings"
    ) as mock_settings:
        mock_settings.return_value.resolved_reports_dir.return_value = reports_dir
        rc = main(["ndr-safe-auto-apply", "--batch", "A", "--dry-run", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert data["emails"] == ["cli@example.cl"]


def test_cli_refuses_apply_flag() -> None:
    with pytest.raises(SystemExit):
        main(["ndr-safe-auto-apply", "--batch", "A", "--apply"])
