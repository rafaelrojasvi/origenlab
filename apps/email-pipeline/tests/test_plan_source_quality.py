from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "plan_source_quality.py"


def _load():
    name = "plan_source_quality_pytest"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_classify_vertical_outbound_reports_tatiana_streamlit_migration() -> None:
    m = _load()
    assert m.classify_vertical("src/origenlab_email_pipeline/outbound_core.py") == "outbound"
    assert m.classify_vertical("src/origenlab_email_pipeline/operational_trust/x.py") == "outbound"
    assert m.classify_vertical("scripts/reports/generate_client_report.py") == "reports"
    assert m.classify_vertical("src/origenlab_email_pipeline/tatiana_copilot/x.py") == "tatiana_lab"
    assert (
        m.classify_vertical("src/origenlab_email_pipeline/tatiana_copilot/openai_chat_generator.py")
        == "tatiana_lab"
    )
    assert m.classify_vertical("src/origenlab_email_pipeline/tatiana_review_cohort.py") == "tatiana_lab"
    assert m.classify_vertical("src/origenlab_email_pipeline/tatiana_voice_cohort.py") == "tatiana_lab"
    assert m.classify_vertical("scripts/tatiana/run_x.py") == "tatiana_lab"
    assert m.classify_vertical("scripts/tatiana/run_something.py") == "tatiana_lab"
    assert m.classify_vertical("scripts/dataset/export_tatiana_candidate_cohort.py") == "tatiana_lab"
    assert m.classify_vertical("scripts/ml/explore_email_clusters.py") == "tatiana_lab"
    assert m.classify_vertical("src/origenlab_email_pipeline/streamlit_foo.py") == "removed_ui_module"
    assert m.classify_vertical("scripts/migrate/sqlite_archive_to_postgres.py") == "postgres_mirror"
    assert m.classify_vertical("src/origenlab_email_pipeline/postgres_outbound_audit.py") == "postgres_mirror"


def test_classify_vertical_production_outbound_not_tatiana_lab() -> None:
    m = _load()
    assert m.classify_vertical("src/origenlab_email_pipeline/candidate_export_gate.py") == "outbound"
    assert m.classify_vertical("scripts/leads/process_broad_marketing_contacts.py") == "outbound"


def test_classify_vertical_suppliers() -> None:
    m = _load()
    assert m.classify_vertical("src/origenlab_email_pipeline/supplier_workbook.py") == "suppliers"


def test_subprocess_and_sqlite_keyword_detection(tmp_path: Path) -> None:
    m = _load()
    p = tmp_path / "t.py"
    p.write_text(
        "import subprocess\nsubprocess.run([x])\n"
        "cur.execute('SELECT 1'); conn.commit()\nINSERT INTO t VALUES (1)\n",
        encoding="utf-8",
    )
    s = m._scan_text(p, "scripts/migrate/x.py")
    assert s.has_subprocess
    assert s.has_sqlite_mutation_keywords


def test_top_n_and_core_import_hint(tmp_path: Path) -> None:
    m = _load()
    d = tmp_path / "s"
    d.mkdir()
    (d / "a.py").write_text("from origenlab_email_pipeline.core.outbound import x\n" * 30, encoding="utf-8")
    (d / "b.py").write_text("x=1\n" * 2, encoding="utf-8")
    scans = m.scan_tree(d.resolve(), "src")
    by_lines = sorted(scans, key=lambda x: -x.line_count)[:1]
    assert by_lines[0].path.endswith("a.py")
    assert by_lines[0].has_core_import_hint


def test_json_out_and_no_tree_mutation(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "a").mkdir(parents=True)
    (root / "a" / "b.py").write_text("# line\n" * 5, encoding="utf-8")
    j = tmp_path / "out.json"
    pre = list(root.rglob("*"))
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--src-dir",
            str(root / "a"),
            "--scripts-dir",
            str(root / "a"),
            "--json-out",
            str(j),
            "--top",
            "3",
        ],
        cwd=str(REPO),
        env={**os.environ},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0
    assert j.is_file()
    data = json.loads(j.read_text(encoding="utf-8"))
    assert "vertical_counts" in data
    assert data["file_counts"]["total"] >= 1
    post = list(root.rglob("*"))
    assert {p for p in pre} == {p for p in post}  # no new/deleted under scanned fixture root


def test_toplevel_import_hint(tmp_path: Path) -> None:
    m = _load()
    p = tmp_path / "imp.py"
    p.write_text("from origenlab_email_pipeline import outbound_core as oc\n", encoding="utf-8")
    sn = m._scan_text(p, "scripts/qa/imp.py")
    assert sn.has_toplevel_import_hint


def test_scan_tree_tatiana_copilot_openai_chat_generator(tmp_path: Path) -> None:
    m = _load()
    pkg = tmp_path / "origenlab_email_pipeline"
    (pkg / "tatiana_copilot").mkdir(parents=True)
    (pkg / "tatiana_copilot" / "openai_chat_generator.py").write_text("# x\n" * 4, encoding="utf-8")
    scans = m.scan_tree(pkg.resolve(), "src")
    assert len(scans) == 1
    assert scans[0].vertical == "tatiana_lab"
    assert scans[0].path.endswith("tatiana_copilot/openai_chat_generator.py")


def test_scan_tree_scripts_tatiana_dataset_ml(tmp_path: Path) -> None:
    m = _load()
    root = tmp_path / "scripts"
    (root / "tatiana").mkdir(parents=True)
    (root / "tatiana" / "run_something.py").write_text("def main():\n  pass\n", encoding="utf-8")
    (root / "dataset").mkdir(parents=True)
    (root / "dataset" / "export_tatiana_candidate_cohort.py").write_text("x=1\n", encoding="utf-8")
    (root / "ml").mkdir(parents=True)
    (root / "ml" / "explore_email_clusters.py").write_text("y=2\n", encoding="utf-8")
    scans = m.scan_tree(root.resolve(), "scripts")
    v_by_tail = {s.path.split("/")[-1]: s.vertical for s in scans}
    assert v_by_tail["run_something.py"] == "tatiana_lab"
    assert v_by_tail["export_tatiana_candidate_cohort.py"] == "tatiana_lab"
    assert v_by_tail["explore_email_clusters.py"] == "tatiana_lab"


def test_scan_tree_production_file_not_tatiana_lab(tmp_path: Path) -> None:
    m = _load()
    pkg = tmp_path / "origenlab_email_pipeline"
    pkg.mkdir()
    (pkg / "candidate_export_gate.py").write_text("# gate\n", encoding="utf-8")
    scans = m.scan_tree(pkg.resolve(), "src")
    assert len(scans) == 1
    assert scans[0].vertical == "outbound"


def test_is_excluded_generated_report_py_skips_reports_trees(tmp_path: Path) -> None:
    m = _load()
    root = tmp_path / "app"
    assert m._is_excluded_generated_report_py(
        root / "reports/local/audit/_audit_runner_snapshot.py",
        app_root=root,
    )
    assert m._is_excluded_generated_report_py(
        root / "reports/out/active/current/plan_snapshot.py",
        app_root=root,
    )
    assert not m._is_excluded_generated_report_py(
        root / "scripts/qa/plan_source_quality.py",
        app_root=root,
    )


def test_iter_py_files_skips_generated_report_artifacts(tmp_path: Path) -> None:
    m = _load()
    root = tmp_path / "app"
    (root / "scripts" / "qa").mkdir(parents=True)
    (root / "scripts" / "qa" / "maintained.py").write_text("x=1\n", encoding="utf-8")
    (root / "reports" / "local" / "deep-structure-audit").mkdir(parents=True)
    (root / "reports" / "local" / "deep-structure-audit" / "_audit_runner_snapshot.py").write_text(
        "# snapshot\n" * 200,
        encoding="utf-8",
    )
    (root / "reports" / "out" / "active" / "current").mkdir(parents=True)
    (root / "reports" / "out" / "active" / "current" / "generated_copy.py").write_text(
        "# copy\n" * 100,
        encoding="utf-8",
    )

    files = m.iter_py_files(root.resolve(), app_root=root)
    assert [p.name for p in files] == ["maintained.py"]

    scans = m.scan_tree(root.resolve(), "scripts", app_root=root)
    assert len(scans) == 1
    assert scans[0].path.endswith("scripts/qa/maintained.py")
