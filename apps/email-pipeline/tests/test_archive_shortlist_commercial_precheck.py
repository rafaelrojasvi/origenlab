"""Tests for archive shortlist × commercial intel precheck (recommendation + read-only CSV)."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.archive_shortlist_commercial_precheck import (
    commercial_precheck_recommendation,
    run_precheck_csv,
)
from origenlab_email_pipeline.candidate_export_gate import GateContext

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "leads" / "precheck_archive_shortlist_commercial.py"


@pytest.mark.parametrize(
    "gate_eligible, cst, ost, pst, expected",
    [
        (False, None, None, None, "drop"),
        (True, None, None, None, "review"),
        (True, {"status": "suppressed"}, None, None, "drop"),
        (True, {"status": "rejected"}, None, None, "drop"),
        (True, {"status": "approved"}, None, None, "keep"),
        (True, {"status": "needs_review"}, None, None, "review"),
        (True, {"status": "new"}, {"status": "approved"}, None, "review"),
        (True, None, {"status": "suppressed"}, None, "drop"),
        (True, {"status": "approved"}, {"status": "approved"}, {"status": "snoozed"}, "review"),
    ],
)
def test_commercial_precheck_recommendation(
    gate_eligible: bool,
    cst: dict | None,
    ost: dict | None,
    pst: dict | None,
    expected: str,
) -> None:
    assert (
        commercial_precheck_recommendation(
            gate_eligible=gate_eligible,
            contact_candidate=cst,
            organization_candidate=ost,
            opportunity_candidate=pst,
        )
        == expected
    )


def test_run_precheck_csv_writes_rows(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE contact_candidate (
          contact_email TEXT PRIMARY KEY,
          org_domain TEXT,
          status TEXT NOT NULL DEFAULT 'new',
          suppression_flags TEXT NOT NULL DEFAULT '',
          rationale_text TEXT NOT NULL DEFAULT '',
          confidence_score REAL NOT NULL DEFAULT 0,
          strength_score REAL NOT NULL DEFAULT 0,
          evidence_count INTEGER NOT NULL DEFAULT 0,
          display_name TEXT,
          provenance_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO contact_candidate (
          contact_email, status, suppression_flags, rationale_text,
          confidence_score, strength_score, evidence_count, created_at, updated_at
        ) VALUES (
          'a@buyer.test', 'suppressed', 'VENDOR_LIKE', 'x', 0.5, 0.5, 1, 't', 't'
        );
        """
    )
    conn.commit()
    conn.close()

    inp = tmp_path / "in.csv"
    inp.write_text(
        "case_id,contact_email,institution_name\n"
        "c1,a@buyer.test,Acme\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    ctx = GateContext(
        sent_recipient_norms=frozenset(),
        suppressed_norms=frozenset(),
        outreach_state_by_email={},
        supplier_domains=frozenset(),
        blocked_domains=frozenset(),
        skip_noise_filter=True,
        skip_supplier_domain_filter=True,
        strict_contact_graph_noise=False,
    )
    conn2 = sqlite3.connect(str(db))
    try:
        summary = run_precheck_csv(conn=conn2, input_path=inp, out_path=out, gate_ctx=ctx)
    finally:
        conn2.close()

    assert summary.rows == 1
    assert summary.drop == 1
    assert summary.review == 0
    assert summary.keep == 0

    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["contact_email"] == "a@buyer.test"
    assert rows[0]["recommendation"] == "drop"
    assert rows[0]["contact_candidate_status"] == "suppressed"
    assert "VENDOR_LIKE" in rows[0]["contact_suppression_flags"]
    assert rows[0]["decision_path"] == "drop_commercial_status"
    assert rows[0]["decision_source"] == "commercial"
    assert rows[0]["trigger_layer"] == "contact"
    assert rows[0]["trigger_status"] == "suppressed"
    assert rows[0]["trigger_reason_codes"] == "VENDOR_LIKE"


def test_precheck_cli_smoke(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    sqlite3.connect(str(db)).executescript("CREATE TABLE x (id INT);").close()
    inp = tmp_path / "in.csv"
    inp.write_text("contact_email,institution_name\nok@example.com,Ex\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--input",
            str(inp),
            "--out",
            str(out),
            "--db",
            str(db),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert out.is_file()
    assert "review" in r.stdout  # no commercial tables -> review
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["decision_path"] == "review_missing_commercial_intel"
    assert rows[0]["trigger_layer"] == "none"
