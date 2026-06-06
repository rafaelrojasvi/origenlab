"""Tests for read-only import/reference surface planner."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "plan_import_surface.py"


def _load():
    name = "plan_import_surface_pytest"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_synthetic_repo(root: Path) -> None:
    src = root / "src" / "origenlab_email_pipeline"
    core = src / "core" / "leads"
    scripts_qa = root / "scripts" / "qa"
    scripts_root = root / "scripts"
    tests = root / "tests"
    docs = root / "docs"
    for d in (core, scripts_qa, tests, docs):
        d.mkdir(parents=True)

    (src / "foo.py").write_text(
        "import origenlab_email_pipeline.bar\n"
        "from origenlab_email_pipeline.core.leads import keys\n",
        encoding="utf-8",
    )
    (src / "bar.py").write_text("x = 1\n", encoding="utf-8")
    (core / "keys.py").write_text("KEY = 1\n", encoding="utf-8")
    (src / "business_mart.py").write_text(
        '"""Implementation currently lives in core."""\nfrom origenlab_email_pipeline.core.mart.business_mart import *\n',
        encoding="utf-8",
    )
    (src / "core" / "mart" / "business_mart.py").parent.mkdir(parents=True, exist_ok=True)
    (src / "core" / "mart" / "business_mart.py").write_text("def build(): pass\n", encoding="utf-8")

    (src / "pkg_inner" / "__init__.py").parent.mkdir(parents=True)
    (src / "pkg_inner" / "__init__.py").write_text("", encoding="utf-8")
    (src / "pkg_inner" / "mod.py").write_text(
        "from . import mod as self_ref\nfrom ..bar import x\n",
        encoding="utf-8",
    )

    (scripts_qa / "run_foo.py").write_text(
        "#!/usr/bin/env python3\n"
        "from origenlab_email_pipeline.foo import x\n"
        "if __name__ == '__main__': pass\n",
        encoding="utf-8",
    )
    (scripts_root / "tools" / "purge_sample.py").parent.mkdir(parents=True)
    (scripts_root / "tools" / "purge_sample.py").write_text("# purge tool\n", encoding="utf-8")

    (tests / "test_foo.py").write_text(
        '"""See scripts/qa/run_foo.py and src/origenlab_email_pipeline/foo.py."""\n',
        encoding="utf-8",
    )
    (docs / "RUNBOOK.md").write_text(
        "Run `uv run origenlab status` daily.\n"
        "Also: `uv run python scripts/qa/run_foo.py`\n"
        "Module: `src/origenlab_email_pipeline/bar.py`\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("See scripts/qa/run_foo.py\n", encoding="utf-8")


def test_detects_import_origenlab_package(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    targets = {e.target_module for e in result.import_edges}
    assert "origenlab_email_pipeline.bar" in targets
    assert any(e.target_module.endswith("core.leads") or "core.leads" in e.target_module for e in result.import_edges)


def test_detects_relative_imports_inside_package(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    kinds = {e.import_kind for e in result.import_edges}
    assert "relative_from" in kinds


def test_detects_docs_script_and_module_references(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    assert "scripts/qa/run_foo.py" in result.doc_script_refs
    assert "src/origenlab_email_pipeline/bar.py" in result.doc_module_refs
    assert "scripts/qa/run_foo.py" in result.test_script_refs


def test_detects_origenlab_command_references(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    assert "status" in result.command_refs


def test_detects_python_scripts_reference(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    assert "scripts/qa/run_foo.py" in result.doc_script_refs


def test_creates_all_csv_and_summary(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    out = tmp_path / "out"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    m.write_reports(result, out)
    expected = [
        "import_edges.csv",
        "module_reference_summary.csv",
        "script_reference_summary.csv",
        "zero_python_import_modules.csv",
        "zero_doc_reference_scripts.csv",
        "command_reference_summary.csv",
        "summary.md",
    ]
    for name in expected:
        assert (out / name).is_file(), name
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "not deletion authority" in summary.lower() or "deletion safety" in summary.lower()


def test_dangerous_purge_script_flagged(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    out = tmp_path / "out"
    result = m.scan_roots(src, tmp_path / "scripts", tmp_path / "tests", tmp_path / "docs")
    m.write_reports(result, out)
    with (out / "script_reference_summary.csv").open(encoding="utf-8") as handle:
        rows = {r["script_path"]: r for r in csv.DictReader(handle)}
    purge = rows["scripts/tools/purge_sample.py"]
    assert purge["dangerous_path"] == "True"


def test_facade_pair_not_zero_import_delete_proof(tmp_path: Path) -> None:
    m = _load()
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    facades = m.detect_facade_pairs(src)
    assert any("business_mart.py" in p for p in facades)


def test_json_cli_mode(tmp_path: Path) -> None:
    _write_synthetic_repo(tmp_path)
    src = tmp_path / "src" / "origenlab_email_pipeline"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--src-dir",
            str(src),
            "--scripts-dir",
            str(tmp_path / "scripts"),
            "--tests-dir",
            str(tmp_path / "tests"),
            "--docs-dir",
            str(tmp_path / "docs"),
            "--out-dir",
            str(tmp_path / "json-out"),
            "--json",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    idx = proc.stdout.index("{")
    report = json.loads(proc.stdout[idx:])
    assert report["import_edge_count"] >= 1


def test_repo_smoke_includes_known_modules() -> None:
    m = _load()
    result = m.scan_roots(
        REPO / "src" / "origenlab_email_pipeline",
        REPO / "scripts",
        REPO / "tests",
        REPO / "docs",
    )
    modules = result.all_py_modules
    scripts = result.all_scripts
    assert "src/origenlab_email_pipeline/warm_case_sender_rules.py" in modules
    assert "src/origenlab_email_pipeline/operator_cli/constants.py" in modules
    assert "scripts/qa/plan_function_surface.py" in scripts
    assert "scripts/qa/audit_institution_grouping.py" in scripts
    assert len(result.import_edges) > 100


def test_repo_cli_exits_zero() -> None:
    out = REPO / "reports" / "local" / "import-surface-audit-test-fixture"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out-dir", str(out)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "import_edges.csv").is_file()
