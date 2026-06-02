from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_contacted_lead_overlap_audit.py"


def _run(db: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--out", str(out), *extra],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _seed(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT,
          email_norm TEXT,
          org_name TEXT,
          domain TEXT,
          domain_norm TEXT,
          fit_bucket TEXT,
          upstream_sync_state TEXT
        );
        CREATE TABLE lead_contact_research (
          lead_id INTEGER PRIMARY KEY,
          contact_research_status TEXT NOT NULL DEFAULT 'contacto_encontrado',
          resolved_domain TEXT,
          resolved_contact_name TEXT,
          resolved_contact_email TEXT,
          contact_source TEXT,
          contact_research_notes TEXT,
          updated_at TEXT NOT NULL DEFAULT '2026-04-21T00:00:00Z',
          updated_by TEXT
        );
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          source_file TEXT,
          folder TEXT,
          date_raw TEXT,
          date_iso TEXT
        );
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT
        );
        CREATE TABLE contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          first_contacted_at TEXT,
          last_contacted_at TEXT,
          source TEXT,
          notes TEXT,
          updated_at TEXT NOT NULL DEFAULT '2026-04-21T00:00:00Z',
          updated_by TEXT,
          lead_id INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO lead_master (id, email, email_norm, org_name, domain, domain_norm, fit_bucket, upstream_sync_state)
        VALUES (?,?,?,?,?,?,?, 'active')
        """,
        [
            (1, "senthit@buyer.test", "senthit@buyer.test", "Buyer One", "buyer.test", "buyer.test", "high_fit"),
            (2, "raw@buyer.test", "raw@buyer.test", "Buyer Two", "buyer.test", "buyer.test", "high_fit"),
            (3, "unique@other.test", "unique@other.test", "Other Org", "other.test", "other.test", "high_fit"),
            (4, "victim@blocked.test", "victim@blocked.test", "Blocked Org", "blocked.test", "blocked.test", "high_fit"),
            (5, "low@low.test", "low@low.test", "Low Org", "low.test", "low.test", "low_fit"),
            (
                6,
                "newperson@inst.test",
                "newperson@inst.test",
                "Institution Alpha Research Lab",
                "inst.test",
                "inst.test",
                "high_fit",
            ),
            (
                7,
                "first@inst.test",
                "first@inst.test",
                "Institution Alpha Research Lab",
                "inst.test",
                "inst.test",
                "high_fit",
            ),
            (
                8,
                "longorg@x.test",
                "longorg@x.test",
                "Institution Alpha Research Lab",
                "x.test",
                "x.test",
                "high_fit",
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO lead_contact_research (
          lead_id, resolved_domain, resolved_contact_email, contact_research_status, updated_at
        ) VALUES (2, 'buyer.test', 'statehit@buyer.test', 'contacto_encontrado', '2026-04-21T00:00:00Z')
        """
    )
    conn.executemany(
        """
        INSERT INTO emails (recipients, source_file, folder, date_raw, date_iso) VALUES (?,?,?,?,?)
        """,
        [
            ("senthit@buyer.test", "gmail:contacto@origenlab.cl/x", "[Gmail]/Enviados", "", "2026-04-20T10:00:00Z"),
            ("other@inst.test", "gmail:contacto@origenlab.cl/x", "[Gmail]/Enviados", "", "2026-04-19T10:00:00Z"),
            ("first@inst.test", "gmail:contacto@origenlab.cl/x", "[Gmail]/Enviados", "", "2026-04-01T00:00:00Z"),
            ("pendinghit@csv.test", "gmail:contacto@origenlab.cl/x", "[Gmail]/Sent Mail", "", "2026-04-18T10:00:00Z"),
        ],
    )
    conn.execute(
        """
        INSERT INTO outreach_contact_state (contact_email_norm, state, last_contacted_at, source, lead_id)
        VALUES ('statehit@buyer.test', 'contacted', '2026-04-10T00:00:00Z', 'unit_test', 2)
        """
    )
    conn.execute(
        "INSERT INTO contact_email_suppression (email, suppression_reason_code) VALUES ('victim@blocked.test', 'dnc')"
    )
    conn.execute(
        """
        INSERT INTO contact_domain_suppression (domain_norm, suppression_reason_text, updated_at, updated_by)
        VALUES ('suppdom.test', 'dnc domain', '2026-04-21T00:00:00Z', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO lead_master (id, email, email_norm, org_name, domain, domain_norm, fit_bucket, upstream_sync_state)
        VALUES (9, 'u@suppdom.test', 'u@suppdom.test', 'SuppDom Org', 'suppdom.test', 'suppdom.test', 'high_fit', 'active')
        """
    )
    conn.commit()
    conn.close()


def _fieldnames() -> list[str]:
    return [
        "lead_id",
        "organization_name",
        "organization_domain",
        "fit_bucket",
        "lead_email",
        "researched_email",
        "pending_research_email",
        "matched_email",
        "matched_domain",
        "match_type",
        "already_contacted",
        "blocked_by_sent",
        "blocked_by_outreach_state",
        "outreach_state",
        "blocked_by_email_suppression",
        "blocked_by_domain_suppression",
        "sent_source",
        "last_contacted_at",
        "outreach_source",
        "confidence",
        "recommended_action",
        "notes",
    ]


def test_exact_lead_email_in_sent_high_confidence(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["1"]
    assert r["match_type"] == "exact_lead_email_sent"
    assert r["confidence"] == "high"
    assert r["recommended_action"] == "skip_already_contacted"
    assert r["blocked_by_sent"] == "1"


def test_researched_email_in_outreach_state(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["2"]
    assert r["match_type"] == "exact_researched_email_state"
    assert r["confidence"] == "high"
    assert r["blocked_by_outreach_state"] == "1"
    assert r["outreach_state"] == "contacted"


def test_pending_research_csv_email_in_sent(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    csv_in = tmp_path / "pending.csv"
    csv_in.write_text(
        "lead_id,org_name,resolved_domain,resolved_contact_email,resolved_contact_name,"
        "contact_source_url,source_type,confidence,notes\n"
        "99,CSV Org,csv.test,pendinghit@csv.test,Name,http://x,deepsearch,high,\n",
        encoding="utf-8",
    )
    run = _run(db, out, "--limit", "200", "--input-research-csv", str(csv_in))
    assert run.returncode == 0, run.stderr + run.stdout
    pend_rows = [r for r in _rows(out) if r["lead_id"] == "99"]
    assert len(pend_rows) == 1
    r = pend_rows[0]
    assert r["match_type"] == "exact_pending_email_sent"
    assert r["pending_research_email"] == "pendinghit@csv.test"


def test_pending_research_csv_padded_contact_header_detected(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    csv_in = tmp_path / "pending_padded.csv"
    csv_in.write_text(
        "lead_id, institution_name                              , contact_email                              \n"
        "100,CSV Padded Org,pendinghit@csv.test\n",
        encoding="utf-8",
    )
    run = _run(db, out, "--limit", "200", "--input-research-csv", str(csv_in))
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["100"]
    assert r["pending_research_email"] == "pendinghit@csv.test"
    assert r["match_type"] == "exact_pending_email_sent"
    assert r["recommended_action"] == "skip_already_contacted"
    assert r["confidence"] == "high"


def test_pending_research_csv_institution_name_preserved(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    csv_in = tmp_path / "pending_institution.csv"
    csv_in.write_text(
        "lead_id,institution_name,source_url,contact_email,confidence,contact_label,region,city\n"
        "101,Institucion Uno,https://example.edu/about,new-contact@example.edu,high,rector,rm,santiago\n",
        encoding="utf-8",
    )
    run = _run(db, out, "--limit", "200", "--input-research-csv", str(csv_in))
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["101"]
    assert r["organization_name"] == "Institucion Uno"
    assert r["pending_research_email"] == "new-contact@example.edu"


def test_pending_research_csv_malformed_extra_columns_do_not_crash(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    csv_in = tmp_path / "pending_malformed.csv"
    # Extra trailing values create DictReader rows with key None -> list[str].
    csv_in.write_text(
        "lead_id,contact_email,institution_name\n"
        "102,pendinghit@csv.test,Malformed Org,extra_col_a,extra_col_b\n",
        encoding="utf-8",
    )
    run = _run(db, out, "--limit", "200", "--input-research-csv", str(csv_in))
    assert run.returncode == 0, run.stderr + run.stdout
    assert "pending malformed CSV rows ignored: 1" in run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["102"]
    assert r["pending_research_email"] == "pendinghit@csv.test"
    assert r["match_type"] == "exact_pending_email_sent"


def test_pending_research_csv_old_resolved_contact_email_still_works(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    csv_in = tmp_path / "pending_old_schema.csv"
    csv_in.write_text(
        "lead_id,org_name,resolved_domain,resolved_contact_email\n"
        "103,Old Schema Org,csv.test,pendinghit@csv.test\n",
        encoding="utf-8",
    )
    run = _run(db, out, "--limit", "200", "--input-research-csv", str(csv_in))
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["103"]
    assert r["pending_research_email"] == "pendinghit@csv.test"
    assert r["match_type"] == "exact_pending_email_sent"


def test_same_domain_review_not_hard_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r = by_id["6"]
    assert r["match_type"] == "same_domain_contacted"
    assert r["confidence"] == "medium"
    assert r["recommended_action"] == "review_same_domain"
    assert r["already_contacted"] == "0"


def test_suppression_email_and_domain(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    assert by_id["4"]["match_type"] == "suppression_email"
    assert by_id["4"]["recommended_action"] == "suppressed_do_not_contact"
    assert by_id["9"]["match_type"] == "suppression_domain"
    assert by_id["9"]["blocked_by_domain_suppression"] == "1"


def test_low_fit_excluded_by_default(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    ids = {r["lead_id"] for r in _rows(out)}
    assert "5" not in ids


def test_include_low_fit(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100", "--include-low-fit")
    assert run.returncode == 0, run.stderr + run.stdout
    ids = {r["lead_id"] for r in _rows(out)}
    assert "5" in ids


def test_golden_lead_id_1_blocked_by_sent_semantics(tmp_path: Path) -> None:
    """Lock minimal row semantics before refactor (lead 1 = Sent hit)."""
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "20")
    assert run.returncode == 0, run.stderr + run.stdout
    r = next(x for x in _rows(out) if x["lead_id"] == "1")
    assert r["blocked_by_sent"] == "1"
    assert r["already_contacted"] == "1"
    assert r["recommended_action"] == "skip_already_contacted"


def test_csv_columns_stable(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "20")
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    assert rows
    assert list(rows[0].keys()) == _fieldnames()


def test_no_writes_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    before = db.read_bytes()
    run = _run(db, out, "--limit", "50")
    assert run.returncode == 0, run.stderr + run.stdout
    assert before == db.read_bytes()


def test_possible_org_name_match_hint(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100")
    assert run.returncode == 0, run.stderr + run.stdout
    by_id = {r["lead_id"]: r for r in _rows(out)}
    r8 = by_id["8"]
    assert r8["match_type"] == "possible_org_name_match"
    assert r8["confidence"] == "low"
    assert r8["recommended_action"] == "review_possible_duplicate_org"
