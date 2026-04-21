from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "export_lead_contact_research_queue.py"


def _run(db: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--out", str(out), *extra],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _seed(db: Path) -> None:
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(db))
    ensure_leads_tables(conn)
    conn.executemany(
        """
        INSERT INTO lead_master (
          id,source_name,source_record_id,org_name,email,email_norm,domain,domain_norm,
          region,city,fit_bucket,priority_score,last_seen_at,upstream_sync_state
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active')
        """,
        [
            (101, "src", "r101", "Org High Missing", "", "", "highmissing.cl", "highmissing.cl", "RM", "SCL", "high_fit", 9.5, "2026-04-21T00:00:00+00:00"),
            (102, "src", "r102", "Org Medium Missing", "", "", "medmissing.cl", "medmissing.cl", "RM", "SCL", "medium_fit", 8.0, "2026-04-20T00:00:00+00:00"),
            (103, "src", "r103", "Org Low", "", "", "low.cl", "low.cl", "RM", "SCL", "low_fit", 7.0, "2026-04-19T00:00:00+00:00"),
            (104, "src", "r104", "Org Researched", "", "", "researched.cl", "researched.cl", "RM", "SCL", "high_fit", 9.0, "2026-04-18T00:00:00+00:00"),
        ],
    )
    conn.execute(
        """
        INSERT INTO lead_contact_research (
          lead_id, contact_research_status, resolved_domain, resolved_contact_name, resolved_contact_email, contact_source, contact_research_notes, updated_at, updated_by
        ) VALUES (104, 'contacto_encontrado', 'researched.cl', 'Ana', 'ana@researched.cl', 'deepsearch', 'ok', '2026-04-21T00:00:00Z', 'qa')
        """
    )
    conn.commit()
    conn.close()


def test_research_queue_core_behavior(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "queue.csv"
    _seed(db)
    run = _run(db, out)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    by_id = {int(r["lead_id"]): r for r in rows}

    assert 101 in by_id  # high_fit missing email appears
    assert 102 in by_id  # medium_fit missing email appears
    assert 103 not in by_id  # low_fit excluded
    assert 104 not in by_id  # researched email excluded by default

    r101 = by_id[101]
    assert r101["needs_contact_research"] == "1"
    assert "Org High Missing contacto compras laboratorio" in r101["research_query_1"]
    assert "site:highmissing.cl contacto compras" == r101["research_query_3"]

    assert list(rows[0].keys()) == [
        "lead_id",
        "organization_name",
        "organization_domain",
        "website",
        "region",
        "city",
        "fit_bucket",
        "priority_score",
        "current_lead_email",
        "current_email_norm",
        "contact_research_status",
        "resolved_contact_email",
        "resolved_domain",
        "needs_contact_research",
        "research_query_1",
        "research_query_2",
        "research_query_3",
        "notes",
    ]


def test_include_existing_research_flag(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "queue.csv"
    _seed(db)
    run = _run(db, out, "--include-existing-research")
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    by_id = {int(r["lead_id"]): r for r in rows}
    assert 104 in by_id
    assert by_id[104]["needs_contact_research"] == "0"
    assert by_id[104]["resolved_contact_email"] == "ana@researched.cl"

