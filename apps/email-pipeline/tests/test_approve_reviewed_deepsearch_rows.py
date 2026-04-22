from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "approve_reviewed_deepsearch_rows.py"
VALIDATOR = REPO / "scripts" / "qa" / "validate_campaign_csvs.py"


def _write_reviewed(path: Path) -> None:
    rows = [
        {
            "lead_id": "1",
            "org_name": "Org A",
            "resolved_domain": "a.cl",
            "resolved_contact_email": "a@a.cl",
            "resolved_contact_name": "A",
            "contact_source_url": "https://a.cl/contacto",
            "source_type": "website",
            "confidence": "high",
            "notes": "",
        },
        {
            "lead_id": "2",
            "org_name": "Org B",
            "resolved_domain": "b.cl",
            "resolved_contact_email": "b@b.cl",
            "resolved_contact_name": "B",
            "contact_source_url": "https://b.cl/contacto",
            "source_type": "website",
            "confidence": "high",
            "notes": "",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_approves_selected_lead_id_only(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), "--approve-lead-id", "2", cwd=REPO)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    assert len(rows) == 1
    assert rows[0]["lead_id"] == "2"


def test_refuses_unknown_lead_id(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), "--approve-lead-id", "999", cwd=REPO)
    assert run.returncode == 2
    assert not out.exists()


def test_refuses_empty_approval(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), cwd=REPO)
    assert run.returncode == 2
    assert not out.exists()


def test_preserves_schema(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), "--approve-email", "a@a.cl", cwd=REPO)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    assert rows
    assert list(rows[0].keys()) == [
        "lead_id",
        "org_name",
        "resolved_domain",
        "resolved_contact_email",
        "resolved_contact_name",
        "contact_source_url",
        "source_type",
        "confidence",
        "notes",
    ]


def test_output_validates_as_reviewed_deepsearch(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), "--approve-lead-id", "1", cwd=REPO)
    assert run.returncode == 0, run.stderr + run.stdout
    v = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--file",
            str(out),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert v.returncode == 0, v.stderr + v.stdout


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    _write_reviewed(inp)
    run = _run("--input", str(inp), "--out", str(out), "--approve-lead-id", "1", "--dry-run", cwd=REPO)
    assert run.returncode == 0, run.stderr + run.stdout
    assert not out.exists()

