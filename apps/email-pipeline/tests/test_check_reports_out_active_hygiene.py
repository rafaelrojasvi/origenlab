from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "check_reports_out_active_hygiene.py"
    )


def test_hygiene_passes_for_allowed_entries(tmp_path: Path) -> None:
    active = tmp_path / "active"
    active.mkdir()
    (active / "current").mkdir()
    (active / "operational_run_manifests").mkdir()
    (active / "README.md").write_text("x\n", encoding="utf-8")
    (active / "CLEANUP_INDEX.md").write_text("x\n", encoding="utf-8")
    (active / "all_known_marketing_contacts_dedup.csv").write_text("contact_email\n", encoding="utf-8")
    (active / "outreach_contacted_all.csv").write_text("contact_email\n", encoding="utf-8")

    cp = subprocess.run(
        [sys.executable, str(_script_path()), "--active-dir", str(active)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["ok"] is True
    assert payload["unexpected_count"] == 0


def test_hygiene_fails_for_legacy_entries(tmp_path: Path) -> None:
    active = tmp_path / "active"
    active.mkdir()
    (active / "current").mkdir()
    (active / "README.md").write_text("x\n", encoding="utf-8")
    (active / "archive_send_batch_old").mkdir()
    (active / "send_ready_marketing.csv").write_text("contact_email\n", encoding="utf-8")

    cp = subprocess.run(
        [sys.executable, str(_script_path()), "--active-dir", str(active)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert cp.returncode == 1, cp.stdout + cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["ok"] is False
    assert payload["unexpected_count"] == 2
    kinds = {item["kind"] for item in payload["unexpected"]}
    assert "legacy_archive_batch_folder" in kinds
    assert "send_artifact_outside_current" in kinds
