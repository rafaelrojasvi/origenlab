from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "tools" / "archive_reports_out_generated.py"


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO / "src")}


def _run(
    *extra: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        cwd=str(cwd),
        env={**_env(), **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _count_files(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file())


def test_dry_run_does_not_create_manual_cleanup(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp" / "a").mkdir(parents=True)
    (root / "tmp" / "a" / "f.txt").write_text("x", encoding="utf-8")
    r = _run("--reports-out-dir", str(root), "--include-tmp", cwd=REPO)
    assert r.returncode == 0
    assert "DRY-RUN" in r.stdout
    assert not (root / "archive" / "manual_cleanup").exists()
    assert (root / "tmp" / "a" / "f.txt").is_file()


def test_apply_requires_archive_slug(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "a.txt").write_text("x", encoding="utf-8")
    r = _run("--reports-out-dir", str(root), "--include-tmp", "--apply", cwd=REPO)
    assert r.returncode == 2
    assert "archive-slug" in (r.stderr or "").lower() or "archive-slug" in (r.stdout or "").lower()


def test_apply_moves_tmp_preserves_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp" / "a").mkdir(parents=True)
    (root / "tmp" / "a" / "f.txt").write_text("hello", encoding="utf-8")
    n_before = _count_files(root)
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--apply",
        "--archive-slug",
        "pytest-move",
        cwd=REPO,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "APPLY" in r.stdout
    mdirs = list((root / "archive" / "manual_cleanup").glob("*"))
    assert len(mdirs) == 1
    dest_file = mdirs[0] / "tmp" / "a" / "f.txt"
    assert dest_file.is_file()
    assert dest_file.read_text(encoding="utf-8") == "hello"
    assert not (root / "tmp" / "a" / "f.txt").exists()
    assert _count_files(root) == n_before


def test_readme_filename_in_path_skipped(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "README.md").write_text("# n", encoding="utf-8")
    (root / "tmp" / "ok.txt").write_text("z", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--apply",
        "--archive-slug",
        "r1",
        cwd=REPO,
    )
    assert r.returncode == 0
    mdirs = list((root / "archive" / "manual_cleanup").glob("*"))
    assert (mdirs[0] / "tmp" / "ok.txt").is_file()
    assert (root / "tmp" / "README.md").is_file()


def test_active_subdir_tmp_bucket_not_moved_without_allow(tmp_path: Path) -> None:
    """``my_`` in planner can classify as tmp even under active/; whole ``active/`` is protected."""
    root = tmp_path / "out"
    (root / "active" / "my_pilot" / "sub").mkdir(parents=True)
    (root / "active" / "my_pilot" / "sub" / "a.txt").write_text("c", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        cwd=REPO,
    )
    assert r.returncode == 0
    assert "files to move: 0" in r.stdout
    assert (root / "active" / "my_pilot" / "sub" / "a.txt").is_file()


def test_active_current_not_moved_without_include_allow(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "active" / "current").mkdir(parents=True)
    (root / "active" / "current" / "x.txt").write_text("c", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--apply",
        "--archive-slug",
        "a1",
        cwd=REPO,
    )
    assert r.returncode == 0
    assert "files to move: 0" in r.stdout
    assert (root / "active" / "current" / "x.txt").is_file()


def test_allow_active_current_moves(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "active" / "current").mkdir(parents=True)
    (root / "active" / "current" / "x.txt").write_text("c", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--allow-active-current",
        "--apply",
        "--archive-slug",
        "a2",
        cwd=REPO,
    )
    assert r.returncode == 0
    mdirs = list((root / "archive" / "manual_cleanup").glob("*"))
    assert len(mdirs) == 1
    assert (mdirs[0] / "active" / "current" / "x.txt").read_text(encoding="utf-8") == "c"
    assert not (root / "active" / "current" / "x.txt").exists()


def test_max_files_blocks_apply(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp").mkdir(parents=True)
    for i in range(3):
        (root / "tmp" / f"f{i}.txt").write_text("x", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--apply",
        "--archive-slug",
        "m1",
        "--max-files",
        "2",
        cwd=REPO,
    )
    assert r.returncode == 3
    for i in range(3):
        assert (root / "tmp" / f"f{i}.txt").is_file()


def test_json_out(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "a.txt").write_text("b", encoding="utf-8")
    jf = tmp_path / "r.json"
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--json-out",
        str(jf),
        cwd=REPO,
    )
    assert r.returncode == 0
    data = json.loads(jf.read_text(encoding="utf-8"))
    assert data["mode"] == "DRY-RUN"
    assert data["file_count"] == 1
    assert len(data["moves"]) == 1
    assert data["moves"][0]["relative"] == "tmp/a.txt"


def test_iter_skips_manual_cleanup_sources(tmp_path: Path) -> None:
    root = tmp_path / "out"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "t.txt").write_text("t", encoding="utf-8")
    (root / "archive" / "manual_cleanup" / "old" / "a").mkdir(parents=True)
    (root / "archive" / "manual_cleanup" / "old" / "a" / "keep.txt").write_text("k", encoding="utf-8")
    r = _run(
        "--reports-out-dir",
        str(root),
        "--include-tmp",
        "--apply",
        "--archive-slug",
        "mc",
        cwd=REPO,
    )
    assert r.returncode == 0
    assert (root / "archive" / "manual_cleanup" / "old" / "a" / "keep.txt").is_file()
    placed = list((root / "archive" / "manual_cleanup").rglob("tmp/t.txt"))
    assert len(placed) == 1
    assert placed[0] != (root / "tmp" / "t.txt")
    assert placed[0].read_text() == "t"
