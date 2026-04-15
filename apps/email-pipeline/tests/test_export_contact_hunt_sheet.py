from __future__ import annotations

import csv
from pathlib import Path


def test_contact_hunt_sorting_prefers_high_fit_and_net_new(tmp_path: Path) -> None:
    """Smoke test: run exporter against a tiny in-memory DB and check ordering rules."""
    # Import here to avoid circulars during test collection.
    from origenlab_email_pipeline.db import connect
    from origenlab_email_pipeline.leads_enrich import derive_product_angle  # noqa: F401
    # The exporter script lives under scripts/, which is added to sys.path in the script itself.
    # We import it as a module via its relative path package-style.
    import importlib.util
    import sys

    script_path = Path("scripts/leads/advanced/export_contact_hunt_sheet.py")
    spec = importlib.util.spec_from_file_location("export_contact_hunt_sheet", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_contact_hunt_sheet"] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    export_main = module.main  # type: ignore[attr-defined]

    db_path = tmp_path / "test.sqlite"
    # Minimal schema: just enough to satisfy exporter.
    conn = connect(db_path)
    conn.executescript(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT,
          source_type TEXT,
          source_record_id TEXT,
          source_url TEXT,
          org_name TEXT,
          contact_name TEXT,
          email TEXT,
          phone TEXT,
          website TEXT,
          domain TEXT,
          region TEXT,
          city TEXT,
          lead_type TEXT,
          organization_type_guess TEXT,
          buyer_kind TEXT,
          equipment_match_tags TEXT,
          lab_context_score REAL,
          lab_context_tags TEXT,
          evidence_summary TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          priority_score REAL,
          priority_reason TEXT,
          fit_bucket TEXT,
          status TEXT,
          review_owner TEXT,
          last_reviewed_at TEXT,
          next_action TEXT,
          notes TEXT
        );
        CREATE TABLE lead_matches_existing_orgs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id INTEGER NOT NULL,
          matched_domain TEXT,
          matched_org_name TEXT,
          match_type TEXT,
          confidence_score REAL,
          already_in_archive_flag INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    # Insert two leads: one high_fit net-new with equipment+URL, one medium_fit already-in-archive without URL.
    conn.execute(
        """
        INSERT INTO lead_master
          (source_name, source_record_id, org_name, region, city, lead_type, organization_type_guess,
           buyer_kind, equipment_match_tags, lab_context_tags,
           evidence_summary, priority_score, priority_reason, fit_bucket,
           status, review_owner, next_action, notes, source_url)
        VALUES
          ('chilecompra', 'lic-a', 'Org A', 'RM', 'Santiago', 'tender_buyer', 'government',
           'hospital', 'balanza', 'laboratorio', 'Licitación balanza', 8.0, 'test', 'high_fit',
           'nuevo', '', '', '', 'http://example.org/a'),
          ('chilecompra', 'lic-b', 'Org B', 'RM', 'Santiago', 'tender_buyer', 'government',
           'publico', '', '', 'Licitación genérica', 5.0, 'test', 'medium_fit',
           'nuevo', '', '', '', '')
        """
    )
    # Mark second lead as already in archive.
    conn.execute(
        "INSERT INTO lead_matches_existing_orgs (lead_id, matched_domain, matched_org_name, match_type, confidence_score, already_in_archive_flag) "
        "VALUES (2, 'b.cl', 'Org B', 'domain', 1.0, 1)"
    )
    conn.commit()
    conn.close()

    # Monkeypatch settings so exporter uses our temp DB.
    # Settings is a Pydantic model; we can just instantiate and override env for this call.
    out_path = tmp_path / "contact_hunt.csv"
    argv_backup = list(__import__("sys").argv)
    __import__("sys").argv = [
        "export_contact_hunt_sheet",
        "--db",
        str(db_path),
        "--out",
        str(out_path),
        "--limit",
        "10",
    ]
    try:
        export_main()
    finally:
        __import__("sys").argv = argv_backup

    # Verify file exists and high_fit net-new row comes first.
    assert out_path.exists()
    with out_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["organizacion_compradora"] == "Org A"
    assert rows[0]["ajuste_fit"] == "high_fit"
    assert rows[0]["ya_en_archivo"] == "0"
    assert rows[1]["organizacion_compradora"] == "Org B"

