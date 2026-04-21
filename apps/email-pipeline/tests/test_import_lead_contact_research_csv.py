from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path


def _load_script():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "leads" / "import_lead_contact_research_csv.py"
    spec = importlib.util.spec_from_file_location("import_lead_contact_research_csv", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_db(db: Path) -> None:
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(db))
    ensure_leads_tables(conn)
    conn.execute(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name, fit_bucket, status, upstream_sync_state
        ) VALUES (101, 'x', 'r101', 'Org A', 'high_fit', 'nuevo', 'active')
        """
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name, fit_bucket, status, upstream_sync_state
        ) VALUES (102, 'x', 'r102', 'Org B', 'medium_fit', 'nuevo', 'active')
        """
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name, fit_bucket, status, upstream_sync_state
        ) VALUES (103, 'x', 'r103', 'Org C', 'medium_fit', 'nuevo', 'active')
        """
    )
    conn.commit()
    conn.close()


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
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
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_import_dry_run_no_write(tmp_path: Path) -> None:
    mod = _load_script()
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    inp = tmp_path / "in.csv"
    _write_csv(
        inp,
        [
            {
                "lead_id": "101",
                "org_name": "Org A",
                "resolved_domain": "orga.cl",
                "resolved_contact_email": "qa@orga.cl",
                "resolved_contact_name": "QA",
                "contact_source_url": "https://orga.cl/contacto",
                "source_type": "deepsearch",
                "confidence": "high",
                "notes": "ok",
            }
        ],
    )

    old = sys.argv
    try:
        sys.argv = [
            "import_lead_contact_research_csv.py",
            "--input",
            str(inp),
            "--db",
            str(db),
            "--dry-run",
        ]
        rc = mod.main()
    finally:
        sys.argv = old
    assert rc == 0

    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT COUNT(*) FROM lead_contact_research").fetchone()[0]
    conn.close()
    assert n == 0


def test_import_apply_and_replace_guard(tmp_path: Path) -> None:
    mod = _load_script()
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    inp = tmp_path / "in.csv"
    _write_csv(
        inp,
        [
            {
                "lead_id": "101",
                "org_name": "Org A",
                "resolved_domain": "orga.cl",
                "resolved_contact_email": "qa@orga.cl",
                "resolved_contact_name": "QA",
                "contact_source_url": "https://orga.cl/contacto",
                "source_type": "deepsearch",
                "confidence": "high",
                "notes": "first",
            }
        ],
    )

    old = sys.argv
    try:
        sys.argv = [
            "import_lead_contact_research_csv.py",
            "--input",
            str(inp),
            "--db",
            str(db),
            "--apply",
        ]
        rc1 = mod.main()
    finally:
        sys.argv = old
    assert rc1 == 0

    # Second import with changed email should skip without --replace-existing.
    _write_csv(
        inp,
        [
            {
                "lead_id": "101",
                "org_name": "Org A",
                "resolved_domain": "orga.cl",
                "resolved_contact_email": "new@orga.cl",
                "resolved_contact_name": "QA2",
                "contact_source_url": "https://orga.cl/contacto2",
                "source_type": "deepsearch",
                "confidence": "high",
                "notes": "second",
            }
        ],
    )
    old = sys.argv
    try:
        sys.argv = [
            "import_lead_contact_research_csv.py",
            "--input",
            str(inp),
            "--db",
            str(db),
            "--apply",
        ]
        rc2 = mod.main()
    finally:
        sys.argv = old
    assert rc2 == 0

    conn = sqlite3.connect(str(db))
    email = conn.execute(
        "SELECT resolved_contact_email FROM lead_contact_research WHERE lead_id=101"
    ).fetchone()[0]
    assert email == "qa@orga.cl"
    conn.close()


def test_import_rejects_high_without_url_and_low_confidence_freemail(tmp_path: Path) -> None:
    mod = _load_script()
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    inp = tmp_path / "in.csv"
    _write_csv(
        inp,
        [
            {
                "lead_id": "102",
                "org_name": "Org B",
                "resolved_domain": "orgb.cl",
                "resolved_contact_email": "ok@orgb.cl",
                "resolved_contact_name": "OK",
                "contact_source_url": "",
                "source_type": "deepsearch",
                "confidence": "high",
                "notes": "missing url",
            },
            {
                "lead_id": "103",
                "org_name": "Org C",
                "resolved_domain": "orgc.cl",
                "resolved_contact_email": "person@gmail.com",
                "resolved_contact_name": "P",
                "contact_source_url": "https://example.com",
                "source_type": "deepsearch",
                "confidence": "low",
                "notes": "freemail",
            },
        ],
    )

    old = sys.argv
    try:
        sys.argv = [
            "import_lead_contact_research_csv.py",
            "--input",
            str(inp),
            "--db",
            str(db),
            "--apply",
        ]
        rc = mod.main()
    finally:
        sys.argv = old
    assert rc == 2

    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT COUNT(*) FROM lead_contact_research").fetchone()[0]
    conn.close()
    assert n == 0


def test_import_rejects_high_confidence_when_source_host_not_official(tmp_path: Path) -> None:
    mod = _load_script()
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    inp = tmp_path / "in.csv"
    _write_csv(
        inp,
        [
            {
                "lead_id": "101",
                "org_name": "Org A",
                "resolved_domain": "orga.cl",
                "resolved_contact_email": "qa@orga.cl",
                "resolved_contact_name": "QA",
                "contact_source_url": "https://random-blog.example.net/post",
                "source_type": "deepsearch",
                "confidence": "high",
                "notes": "url host mismatch",
            }
        ],
    )

    old = sys.argv
    try:
        sys.argv = [
            "import_lead_contact_research_csv.py",
            "--input",
            str(inp),
            "--db",
            str(db),
            "--apply",
        ]
        rc = mod.main()
    finally:
        sys.argv = old
    assert rc == 2

    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT COUNT(*) FROM lead_contact_research").fetchone()[0]
    conn.close()
    assert n == 0
