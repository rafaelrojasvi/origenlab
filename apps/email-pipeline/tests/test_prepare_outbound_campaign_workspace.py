from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_script():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "qa" / "prepare_outbound_campaign_workspace.py"
    spec = importlib.util.spec_from_file_location("prepare_outbound_campaign_workspace", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main(mod, cwd: Path, *args: str) -> int:
    old_argv = sys.argv
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        reports_out = cwd / "reports" / "out"
        sys.argv = [
            "prepare_outbound_campaign_workspace.py",
            "--reports-out-dir",
            str(reports_out),
            *args,
        ]
        return int(mod.main())
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


def _canonical_names() -> set[str]:
    return {
        "research_queue.csv",
        "reviewed_deepsearch.csv",
        "overlap_audit.csv",
        "gate_audit.csv",
        "send_ready.csv",
        "outbound_summary.json",
        "send_manifest.json",
        "mark_contacted_result.json",
        "campaign_manifest.json",
    }


def test_creates_current_workspace_and_manifest(tmp_path: Path) -> None:
    mod = _load_script()
    code = _run_main(mod, tmp_path, "--campaign-slug", "Q2-Hospitals", "--operator", "rafael")
    assert code == 0
    current = tmp_path / "reports" / "out" / "active" / "current"
    assert current.is_dir()
    assert _canonical_names().issubset({p.name for p in current.iterdir()})

    manifest = json.loads((current / "campaign_manifest.json").read_text(encoding="utf-8"))
    assert manifest["campaign_slug"] == "Q2-Hospitals"
    assert manifest["operator"] == "rafael"
    assert isinstance(manifest["created_at"], str) and manifest["created_at"]
    assert "current_paths" in manifest
    assert "recommended_next_steps" in manifest
    assert "notes" in manifest


def test_archive_existing_moves_previous_files(tmp_path: Path) -> None:
    mod = _load_script()
    current = tmp_path / "reports" / "out" / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    (current / "old.csv").write_text("x\n", encoding="utf-8")
    (current / "nested").mkdir()
    (current / "nested" / "a.txt").write_text("hello", encoding="utf-8")

    code = _run_main(mod, tmp_path, "--campaign-slug", "my-campaign", "--archive-existing")
    assert code == 0
    archive_root = tmp_path / "reports" / "out" / "archive"
    archives = [p for p in archive_root.iterdir() if p.is_dir()]
    assert archives, "expected archive directory to be created"
    archived = archives[0]
    assert (archived / "old.csv").exists()
    assert (archived / "nested" / "a.txt").exists()
    assert _canonical_names().issubset({p.name for p in current.iterdir()})


def test_manifest_contains_canonical_paths(tmp_path: Path) -> None:
    mod = _load_script()
    code = _run_main(mod, tmp_path, "--campaign-slug", "path-check")
    assert code == 0
    current = tmp_path / "reports" / "out" / "active" / "current"
    manifest = json.loads((current / "campaign_manifest.json").read_text(encoding="utf-8"))
    cp = manifest["current_paths"]
    assert cp["research_queue"].endswith("reports/out/active/current/research_queue.csv")
    assert cp["reviewed_deepsearch"].endswith("reports/out/active/current/reviewed_deepsearch.csv")
    assert cp["overlap_audit"].endswith("reports/out/active/current/overlap_audit.csv")
    assert cp["gate_audit"].endswith("reports/out/active/current/gate_audit.csv")
    assert cp["send_ready"].endswith("reports/out/active/current/send_ready.csv")
    assert cp["campaign_manifest"].endswith("reports/out/active/current/campaign_manifest.json")


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    mod = _load_script()
    code = _run_main(mod, tmp_path, "--campaign-slug", "dry", "--archive-existing", "--dry-run")
    assert code == 0
    assert not (tmp_path / "reports").exists()


def test_does_not_touch_db_file(tmp_path: Path) -> None:
    mod = _load_script()
    db = tmp_path / "emails.sqlite"
    db.write_bytes(b"sqlite-placeholder")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    code = _run_main(mod, tmp_path, "--campaign-slug", "db-safe")
    assert code == 0
    after = hashlib.sha256(db.read_bytes()).hexdigest()
    assert before == after

