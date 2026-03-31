"""Supplier workbook normalization, validation, and import."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook

from origenlab_email_pipeline.supplier_workbook import (
    TIER_ANEXO,
    TIER_EXCLUSION,
    TIER_TOP15,
    TIER_TOP50,
    collect_workbook_validation_issues,
    import_supplier_workbook,
    normalize_supplier_domain,
    partition_supplier_validation_issues,
)
from origenlab_email_pipeline.supplier_schema import ensure_supplier_tables


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _write_minimal_workbook(path: Path) -> None:
    wb = Workbook()
    r = wb.active
    r.title = "Resumen"
    r.append(["Campo", "Valor"])
    r.append(["Versión", "test-fixture"])

    op = wb.create_sheet("Oportunidades_50")
    op.append(["Dominio", "Empresa", "Región", "Ranking", "Confianza", "Foco"])
    op.append(["https://www.alpha.example.com", "Alpha", "Europa", 2, 0.85, "centrífugas"])
    op.append(["beta.example.com", "Beta", "Asia", 1, "90%", "microscopios"])

    c15 = wb.create_sheet("Contacto_15")
    c15.append(["Dominio", "Email contacto", "Formulario"])
    c15.append(["alpha.example.com", "sales@alpha.example.com", "https://alpha.example.com/contact"])

    ev = wb.create_sheet("Evidencias")
    ev.append(["Dominio", "URL", "Título"])
    ev.append(
        [
            "alpha.example.com",
            "https://catalog.alpha.example.com/listing",
            "Catálogo",
        ]
    )

    pr = wb.create_sheet("Prioridades")
    pr.append(["Categoría", "Prioridad"])
    pr.append(["centrífugas", 1])

    ex = wb.create_sheet("Exclusiones")
    ex.append(["Dominio", "Motivo"])
    ex.append(["legacy-old.com", "histórico"])

    ax = wb.create_sheet("Anexo_CSV_NoRepetido")
    ax.append(["Dominio", "Empresa", "Región", "Ranking"])
    ax.append(["gamma.example.org", "Gamma SA", "LATAM", 10])

    wb.save(path)


def test_normalize_supplier_domain_strips_www_and_lower() -> None:
    assert normalize_supplier_domain("HTTPS://WWW.FOO.COM/path") == "foo.com"
    assert normalize_supplier_domain("delta.io") == "delta.io"


def test_collect_validation_finds_annex_overlap(tmp_path: Path) -> None:
    p = tmp_path / "dup.xlsx"
    _write_minimal_workbook(p)
    wb = Workbook()
    # Rebuild with annex duplicate of op50
    wb = Workbook()
    s = wb.active
    s.title = "Resumen"
    s.append(["k", "v"])
    op = wb.create_sheet("Oportunidades_50")
    op.append(["Dominio", "Empresa"])
    op.append(["a.com", "A"])
    c15 = wb.create_sheet("Contacto_15")
    c15.append(["Dominio"])
    c15.append(["a.com"])
    ev = wb.create_sheet("Evidencias")
    ev.append(["Dominio", "URL"])
    ev.append(["a.com", "https://x.com/e"])
    pr = wb.create_sheet("Prioridades")
    pr.append(["c", "p"])
    ex = wb.create_sheet("Exclusiones")
    ex.append(["Dominio"])
    ax = wb.create_sheet("Anexo_CSV_NoRepetido")
    ax.append(["Dominio"])
    ax.append(["a.com"])  # overlap
    wb.save(p)

    issues = collect_workbook_validation_issues(p)
    assert any(x.startswith("anexo_overlap_op50:") for x in issues)


def test_partition_validation() -> None:
    err, warn = partition_supplier_validation_issues(
        ["missing_sheet:foo", "contacto_15_not_subset_op50:b.com"]
    )
    assert any("missing_sheet" in x for x in err)
    assert any("contacto" in x for x in warn)


def test_import_creates_masters_evidence_snapshot(tmp_path: Path) -> None:
    p = tmp_path / "ok.xlsx"
    _write_minimal_workbook(p)
    conn = _conn()
    ensure_supplier_tables(conn)
    bid = import_supplier_workbook(conn, p)
    assert bid >= 1
    n_master = conn.execute("SELECT COUNT(*) FROM supplier_master").fetchone()[0]
    assert n_master >= 4
    alphas = conn.execute(
        "SELECT id FROM supplier_master WHERE domain_norm='alpha.example.com'"
    ).fetchone()
    assert alphas
    sid = int(alphas[0])
    tier = conn.execute(
        "SELECT tier FROM supplier_priority_snapshot WHERE supplier_id=? AND batch_id=?",
        (sid, bid),
    ).fetchone()[0]
    assert tier == TIER_TOP15
    n_ev = conn.execute(
        "SELECT COUNT(*) FROM supplier_evidence WHERE supplier_id=?", (sid,)
    ).fetchone()[0]
    assert n_ev >= 1
    ch = conn.execute(
        "SELECT channel_type FROM supplier_contact_channel WHERE supplier_id=? AND channel_type='email'",
        (sid,),
    ).fetchone()
    assert ch is not None


def test_annex_tier_recorded(tmp_path: Path) -> None:
    p = tmp_path / "ok.xlsx"
    _write_minimal_workbook(p)
    conn = _conn()
    ensure_supplier_tables(conn)
    bid = import_supplier_workbook(conn, p)
    row = conn.execute(
        "SELECT tier FROM supplier_priority_snapshot sm JOIN supplier_master m ON m.id=sm.supplier_id "
        "WHERE m.domain_norm='gamma.example.org' AND sm.batch_id=?",
        (bid,),
    ).fetchone()
    assert row and row[0] == TIER_ANEXO


def test_top50_snapshot_upgraded_by_contact15(tmp_path: Path) -> None:
    p = tmp_path / "ok.xlsx"
    _write_minimal_workbook(p)
    conn = _conn()
    ensure_supplier_tables(conn)
    bid = import_supplier_workbook(conn, p)
    # beta only in op50, not contact15 -> tier top50
    row = conn.execute(
        "SELECT tier FROM supplier_priority_snapshot sm JOIN supplier_master m ON m.id=sm.supplier_id "
        "WHERE m.domain_norm='beta.example.com' AND sm.batch_id=?",
        (bid,),
    ).fetchone()
    assert row and row[0] == TIER_TOP50


def test_exclusion_keeps_flag_when_re_import_candidate(tmp_path: Path) -> None:
    p = tmp_path / "ex.xlsx"
    wb = Workbook()
    wb.active.title = "Resumen"
    wb.active.append(["a", "b"])
    for title, rows in [
        ("Oportunidades_50", [["Dominio", "Empresa"], ["both.com", "Both"]]),
        ("Contacto_15", [["Dominio"], ["both.com"]]),
        ("Evidencias", [["Dominio", "URL"], ["both.com", "https://u.example/x"]]),
        ("Prioridades", [["c"], [1]]),
        ("Exclusiones", [["Dominio"], ["both.com"]]),
        ("Anexo_CSV_NoRepetido", [["Dominio"], ["z99.com"]]),
    ]:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    wb.save(p)
    conn = _conn()
    ensure_supplier_tables(conn)
    bid = import_supplier_workbook(conn, p)
    excl = conn.execute(
        "SELECT is_exclusion FROM supplier_master WHERE domain_norm='both.com'"
    ).fetchone()[0]
    assert int(excl) == 1
    tier = conn.execute(
        "SELECT tier FROM supplier_priority_snapshot sm "
        "JOIN supplier_master m ON m.id=sm.supplier_id "
        "WHERE m.domain_norm='both.com' AND sm.batch_id=?",
        (bid,),
    ).fetchone()[0]
    assert tier == TIER_EXCLUSION
