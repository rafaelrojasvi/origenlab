from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "plan_reports_out_cleanup.py"


def _load_planner():
    name = "plan_reports_out_cleanup_pytest"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _run(
    *extra: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        cwd=str(cwd),
        env=e,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_classify_active_current() -> None:
    m = _load_planner()
    assert m.classify_path(Path("active/current/campaign/a.csv")) == "active_current"


def test_classify_reference() -> None:
    m = _load_planner()
    assert m.classify_path(Path("reference/keep/x.txt")) == "reference"


def test_classify_archive() -> None:
    m = _load_planner()
    assert m.classify_path(Path("archive/2024/z.json")) == "archive"


def test_classify_tatiana_lab() -> None:
    m = _load_planner()
    assert m.classify_path(Path("pilot_tatiana_out/draft.md")) == "lab_or_tatiana"


def test_classify_loose_root() -> None:
    m = _load_planner()
    assert m.classify_path(Path("stray.json")) == "loose_root_files"


def test_classify_client_pack_latest() -> None:
    m = _load_planner()
    assert m.classify_path(Path("client_pack_latest/summary.json")) == "client_pack_latest"


def test_classify_active_workspace_misc() -> None:
    m = _load_planner()
    assert m.classify_path(Path("active/foo.csv")) == "active_workspace_misc"
    assert (
        m.classify_path(Path("active/archive_vs_lead_compare/out.csv")) == "active_workspace_misc"
    )


def test_classify_active_my_prefix_under_active_is_workspace_misc_not_tmp() -> None:
    m = _load_planner()
    assert m.classify_path(Path("active/my_pilot/x.txt")) == "active_workspace_misc"


def test_classify_tmp_behavior_unchanged_outside_active() -> None:
    m = _load_planner()
    assert m.classify_path(Path("my_lead_batch/a.txt")) == "tmp_or_scratch"
    assert m.classify_path(Path("full_20260324_135824/x.html")) == "tmp_or_scratch"


def test_run_planner_on_fake_tree_exits_0(tmp_path: Path) -> None:
    root = tmp_path / "reports" / "out"
    (root / "active" / "current").mkdir(parents=True)
    (root / "active" / "current" / "a.txt").write_text("x", encoding="utf-8")
    (root / "reference" / "r").mkdir(parents=True)
    (root / "reference" / "r" / "evidence.md").write_text("e", encoding="utf-8")
    (root / "archive" / "z").mkdir(parents=True)
    (root / "archive" / "z" / "h.csv").write_text("h", encoding="utf-8")
    (root / "pilot_tatiana").mkdir()
    (root / "pilot_tatiana" / "f.txt").write_text("t", encoding="utf-8")
    (root / "loose.txt").write_text("l", encoding="utf-8")
    (root / "active" / "batch.csv").write_text("b", encoding="utf-8")
    (root / "client_pack_latest").mkdir()
    (root / "client_pack_latest" / "index.html").write_text("<p/>", encoding="utf-8")
    big = b"x" * (6 * 1024 * 1024)
    (root / "big.bin").write_bytes(big)
    (root / "README.md").write_text("# r", encoding="utf-8")

    r = _run(
        "--reports-out-dir",
        str(root),
        "--large-threshold-mb",
        "5",
        "--top",
        "5",
        cwd=REPO,
    )
    assert r.returncode == 0
    out = r.stdout
    assert "active_current" in out
    assert "reference" in out
    assert "archive" in out
    assert "lab_or_tatiana" in out
    assert "loose_root_files" in out
    assert "active_workspace_misc" in out
    assert "client_pack_latest" in out
    assert "big.bin" in out
    assert "do not commit" in out.lower() or "do not commit" in out
    pre = {p for p in root.rglob("*") if p.is_file()}
    r2 = _run(
        "--reports-out-dir",
        str(root),
        cwd=REPO,
    )
    post = {p for p in root.rglob("*") if p.is_file()}
    assert r2.returncode == 0
    assert pre == post  # no deletes/moves/renames under fake tree


def test_json_out_writes_report(tmp_path: Path) -> None:
    root = tmp_path / "rout"
    (root / "a").mkdir(parents=True)
    (root / "a" / "b.txt").write_text("bb", encoding="utf-8")
    jpath = tmp_path / "plan.json"
    r = _run(
        "--reports-out-dir",
        str(root),
        "--json-out",
        str(jpath),
        cwd=REPO,
    )
    assert r.returncode == 0
    assert jpath.is_file()
    data = json.loads(jpath.read_text(encoding="utf-8"))
    assert data["file_count"] == 1
    assert data["by_bucket"] is not None
    pre = list(root.rglob("*"))
    assert len(list(root.rglob("*"))) == len(pre)  # reports tree unchanged in size
    assert "wrote json report" in (r.stdout or "")
