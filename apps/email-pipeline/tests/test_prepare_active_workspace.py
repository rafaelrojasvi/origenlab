"""Tests for prepare_active_workspace."""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest


def _load_script():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "leads" / "advanced" / "prepare_active_workspace.py"
    spec = importlib.util.spec_from_file_location("prepare_active_workspace", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_focus_and_hunt(active: Path) -> None:
    with (active / "leads_weekly_focus.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id_lead",
                "fit_bucket",
                "priority_score",
                "org_name",
                "buyer_kind",
                "equipment_match_tags",
                "lab_context_score",
                "already_in_archive_flag",
                "source_url",
                "evidence_summary",
                "status",
                "next_action",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "id_lead": "99",
                "fit_bucket": "high_fit",
                "priority_score": "7",
                "org_name": "Org",
                "buyer_kind": "hospital",
                "equipment_match_tags": "balanza",
                "lab_context_score": "1",
                "already_in_archive_flag": "0",
                "source_url": "https://x.cl",
                "evidence_summary": "ev",
                "status": "nuevo",
                "next_action": "",
            }
        )

    with (active / "leads_contact_hunt_current.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "organizacion_compradora", "email_publico_compras"])
        w.writeheader()
        w.writerow({"id_lead": "99", "organizacion_compradora": "Org", "email_publico_compras": "a@b.cl"})


def _run_main(mod, argv: list[str]) -> tuple[int, str]:
    old = sys.argv
    buf = io.StringIO()
    try:
        sys.argv = argv
        with redirect_stdout(buf):
            code = mod.main()
    finally:
        sys.argv = old
    return code, buf.getvalue()


def test_prepare_archives_derivatives_and_builds_unified_with_apply(tmp_path: Path) -> None:
    mod = _load_script()
    active = tmp_path / "reports" / "out" / "active"
    active.mkdir(parents=True, exist_ok=True)
    (active / "leads_shortlist.csv").write_text("x\n", encoding="utf-8")
    (active / "leads_contact_hunt_current_con_db.csv").write_text("x\n", encoding="utf-8")
    _write_focus_and_hunt(active)

    code, _ = _run_main(
        mod,
        [
            "prepare_active_workspace.py",
            "--active-dir",
            str(active),
            "--unified",
            "--apply",
        ],
    )
    assert code == 0
    assert not (active / "leads_shortlist.csv").exists()
    assert not (active / "leads_contact_hunt_current_con_db.csv").exists()
    uni = active / "leads_active_unified.csv"
    assert uni.exists()
    with uni.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["id_lead"] == "99"
    assert rows[0]["email_publico_compras"] == "a@b.cl"


def test_default_run_is_plan_only(tmp_path: Path) -> None:
    mod = _load_script()
    active = tmp_path / "reports" / "out" / "active"
    active.mkdir(parents=True, exist_ok=True)
    (active / "leads_shortlist.csv").write_text("x\n", encoding="utf-8")
    (active / "leads_contact_hunt_current_con_db.csv").write_text("x\n", encoding="utf-8")
    _write_focus_and_hunt(active)

    code, out = _run_main(
        mod,
        [
            "prepare_active_workspace.py",
            "--active-dir",
            str(active),
            "--unified",
        ],
    )
    assert code == 0
    assert (active / "leads_shortlist.csv").exists()
    assert (active / "leads_contact_hunt_current_con_db.csv").exists()
    assert not (active / "leads_active_unified.csv").exists()
    assert "plan only" in out.lower() or "--apply" in out.lower()


def test_dry_run_and_apply_together_rejected(tmp_path: Path) -> None:
    mod = _load_script()
    active = tmp_path / "reports" / "out" / "active"
    active.mkdir(parents=True, exist_ok=True)

    with pytest.raises(SystemExit) as exc:
        _run_main(
            mod,
            [
                "prepare_active_workspace.py",
                "--active-dir",
                str(active),
                "--dry-run",
                "--apply",
            ],
        )
    assert exc.value.code != 0
