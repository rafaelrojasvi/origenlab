from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "plan_script_consolidation.py"


def _load():
    name = "plan_script_consolidation_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_classify_daily_from_map(tmp_path: Path) -> None:
    m = _load()
    mpath = tmp_path / "SCRIPT_MAP.md"
    mpath.write_text(
        "| Path | Tag | Role |\n"
        "|------|-----|------|\n"
        "| `scripts/qa/z_daily.py` | OPS_DAILY | x |\n",
        encoding="utf-8",
    )
    tset = m.parse_map_tags(mpath)
    b = m.classify("qa/z_daily.py", "z_daily.py", "qa", "x", 1, tset, set())
    assert b == "daily"


def test_break_glass_header() -> None:
    m = _load()
    text = "# DANGEROUS: test\n" + "x" * 100
    br = m.is_break_glass("x/p.py", "p.py", "x", text, set())
    assert br is True


def test_apply_and_mutation_detection() -> None:
    m = _load()
    t = "import argparse\nif True:\n  conn.execute('DELETE FROM t')\n  # --apply\n"
    assert m._APPLY.search(t)  # type: ignore[attr-defined]
    assert m._MUT.search(t)  # type: ignore[attr-defined]
    t2 = "Gmail API send_message("
    assert m._SEND.search(t2)  # type: ignore[attr-defined]


def test_read_only_planner_not_break_glass() -> None:
    m = _load()
    t = '"""read-only\nno glass\n"""'
    assert m.is_break_glass("qa/plan_x.py", "plan_x.py", "qa", t, set()) is False


def test_wrapper_candidate() -> None:
    m = _load()
    # subprocess + "leads" in body, line count in range
    text = "import sys\n# leads\n" + "x\n" * 2 + "import subprocess\nsubprocess.run(['a'])\n"
    n = text.count("\n") + 1
    assert m.is_wrapper(n, text) is True


def test_classify_unknown() -> None:
    m = _load()
    b = m.classify("odd/foo.py", "foo.py", "odd", "x", 50, {}, set())
    assert b == "unknown"


def test_classify_bootstrap_infrastructure() -> None:
    m = _load()
    b = m.classify("_bootstrap.py", "_bootstrap.py", "_bootstrap.py", "x", 5, {}, set())
    assert b == "infrastructure_core"
    assert m.action_for("infrastructure_core", True, "_bootstrap.py") == "keep"


def test_classify_chilecompra_and_supplier_workbook() -> None:
    m = _load()
    assert (
        m.classify(
            "qa/extract_chilecompra_lab_buyers_from_xlsx.py",
            "extract_chilecompra_lab_buyers_from_xlsx.py",
            "qa",
            "x",
            10,
            {},
            set(),
        )
        == "maintenance"
    )
    assert (
        m.classify("validate_supplier_workbook.py", "validate_supplier_workbook.py", "validate_supplier_workbook.py", "x", 10, {}, set())
        == "maintenance"
    )
    assert m.action_for("maintenance", False, "validate_supplier_workbook.py") == "keep_maintenance"


def test_classify_compatibility_root_wrappers() -> None:
    m = _load()
    b = m.classify(
        "build_lead_account_rollup.py",
        "build_lead_account_rollup.py",
        "build_lead_account_rollup.py",
        "x",
        20,
        {},
        set(),
    )
    assert b == "compatibility_wrapper"
    assert m.action_for("compatibility_wrapper", True, "build_lead_account_rollup.py") == "keep"


def test_subprocess_and_json(
    tmp_path: Path,
) -> None:
    sroot = tmp_path / "s"
    (sroot / "ingest").mkdir(parents=True)
    (sroot / "ingest" / "05_workspace_gmail_imap_to_sqlite.py").write_text(  # maintenance path
        "# t\n" + "u" * 20,
        encoding="utf-8",
    )
    mpath = tmp_path / "map.md"
    mpath.write_text(  # no rows — classify by path
        "\n", encoding="utf-8",
    )
    droot = tmp_path / "root"
    (droot / "docs").mkdir(parents=True)
    (droot / "tests").mkdir()
    (droot / "docs" / "x.md").write_text("refs scripts/ingest/05_workspace_gmail_imap_to_sqlite.py", encoding="utf-8")
    (droot / "tests" / "t.py").write_text("scripts/ingest/05", encoding="utf-8")
    mod = _load()
    rows = mod.scan(sroot, mpath, app_root=droot)
    assert any(r.path.endswith("ingest/05_workspace_gmail_imap_to_sqlite.py") for r in rows)  # noqa: SIM201
    pre = {p for p in sroot.rglob("*") if p.is_file()}
    jout = tmp_path / "out.json"
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scripts-dir",
            str(sroot),
            "--map",
            str(mpath),
            "--json-out",
            str(jout),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(jout.read_text(encoding="utf-8"))
    assert "rows" in data
    post = {p for p in sroot.rglob("*") if p.is_file()}
    assert pre == post


def test_migrate_bucket(tmp_path: Path) -> None:
    m = _load()
    (mroot := tmp_path / "m").mkdir()
    (mroot / "migrate").mkdir()
    p = mroot / "migrate" / "a.py"
    p.write_text("x", encoding="utf-8")
    mp = tmp_path / "map.md"
    mp.write_text("", encoding="utf-8")
    rows = m.scan(mroot, mp, app_root=tmp_path)
    mrow = [x for x in rows if "migrate/a" in x.path]  # noqa: SIM201
    assert mrow[0].primary_bucket == "migration"  # noqa: SIM201
