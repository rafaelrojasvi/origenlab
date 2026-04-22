from __future__ import annotations

from pathlib import Path

from origenlab_email_pipeline.core import reports_out as r


def test_classify_active_current() -> None:
    assert r.classify_path(Path("active/current/campaign/a.csv")) == "active_current"


def test_classify_reference() -> None:
    assert r.classify_path(Path("reference/keep/x.txt")) == "reference"


def test_classify_archive() -> None:
    assert r.classify_path(Path("archive/2024/z.json")) == "archive"
    assert r.classify_path(Path("old_2020_run/keep")) == "archive"


def test_classify_tatiana_lab() -> None:
    assert r.classify_path(Path("pilot_tatiana_out/draft.md")) == "lab_or_tatiana"
    assert r.classify_path(Path("x/ml_runs/log.txt")) == "lab_or_tatiana"


def test_classify_loose_root() -> None:
    assert r.classify_path(Path("stray.json")) == "loose_root_files"


def test_classify_client_pack_latest() -> None:
    assert r.classify_path(Path("client_pack_latest/summary.json")) == "client_pack_latest"


def test_classify_active_workspace_misc() -> None:
    assert r.classify_path(Path("active/foo.csv")) == "active_workspace_misc"
    assert r.classify_path(Path("active/archive_vs_lead_compare/out.csv")) == "active_workspace_misc"


def test_classify_active_my_prefix_under_active_is_workspace_misc_not_tmp() -> None:
    assert r.classify_path(Path("active/my_pilot/x.txt")) == "active_workspace_misc"


def test_classify_tmp_outside_active() -> None:
    assert r.classify_path(Path("my_lead_batch/a.txt")) == "tmp_or_scratch"
    assert r.classify_path(Path("full_20260324_135824/x.html")) == "tmp_or_scratch"
    assert r.classify_path(Path("tmp/nested/f.txt")) == "tmp_or_scratch"


def test_repo_bootstrap() -> None:
    assert r.classify_path(Path("README.md")) == "repo_bootstrap"


def test_classify_unknown_dir_single_segment() -> None:
    assert r.classify_path(Path("weird")) == "unknown"


def test_manual_cleanup_under_archive() -> None:
    p = Path("archive/manual_cleanup/2020-01-01_s/x.txt")
    assert r.is_under_manual_cleanup(p) is True
    assert r.is_under_manual_cleanup(Path("archive/z.txt")) is False


def test_protected_basename() -> None:
    assert r.path_has_protected_artifact_basename(Path("tmp/README.md")) is True
    assert r.path_has_protected_artifact_basename(Path("tmp/ok.txt")) is False
    assert r.is_protected_artifact_basename(".gitkeep") is True


def test_top_level_active() -> None:
    assert r.is_under_top_level_active(Path("active/current/x")) is True
    assert r.is_under_top_level_active(Path("tmp/x")) is False


def test_bucket_move_eligible_matches_archiver() -> None:
    assert r.bucket_eligible_for_move("tmp_or_scratch", include_tmp=True, include_lab=False, include_loose_root=False, include_unknown=False, allow_active_current=False, allow_reference=False) is True
    assert r.bucket_eligible_for_move("active_current", include_tmp=False, include_lab=False, include_loose_root=False, include_unknown=False, allow_active_current=False, allow_reference=False) is False
    assert r.bucket_eligible_for_move("active_current", include_tmp=False, include_lab=False, include_loose_root=False, include_unknown=False, allow_active_current=True, allow_reference=False) is True
    assert r.bucket_eligible_for_move("archive", include_tmp=True, include_lab=True, include_loose_root=True, include_unknown=True, allow_active_current=True, allow_reference=True) is False


def test_proposed_action_keys() -> None:
    assert "active_current" in r.PROPOSED_ACTION
    assert "large_files" in r.PROPOSED_ACTION
    assert "large_files" in r.PROPOSED_ACTION_PRINT_ORDER


def test_by_bucket_aggregation() -> None:
    entries = [
        r.FileEntry("a.txt", 10, "unknown", False),
        r.FileEntry("b.txt", 10, "unknown", False),
    ]
    agg = r.by_bucket_aggregation(entries)
    assert agg["unknown"]["file_count"] == 2
    assert agg["unknown"]["total_bytes"] == 20


def test_scan_reports_out_no_mutation(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "reference").mkdir(parents=True)
    f = root / "reference" / "x.md"
    f.write_text("z", encoding="utf-8")
    entries, n, total = r.scan_reports_out(root, 999)
    assert n == 1
    assert total == 1
    pre = f.read_text()
    entries2, _, _ = r.scan_reports_out(root, 0)
    assert f.read_text() == pre
    assert entries2[0].primary_bucket == "reference"
