from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_intel_review import (
    QueueFilters,
    apply_review_action,
    export_queue_csv,
    fetch_queue_rows,
)
from origenlab_email_pipeline.db import connect, insert_email
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


@pytest.fixture()
def review_db(tmp_path: Path) -> Path:
    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    try:
        migrate_sqlite_schema(
            conn,
            layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL},
        )
        now = "2026-03-28T12:00:00Z"
        conn.execute(
            """
            INSERT INTO organization_candidate
            (org_domain, display_name, candidate_type, status, confidence_score, strength_score, evidence_count,
             latest_activity_at, suppression_flags, rationale_text, provenance_json, created_at, updated_at)
            VALUES (?, ?, 'net_new', 'needs_review', 0.72, 0.41, 3, ?, '', 'Org rollup summary.', '{}', ?, ?)
            """,
            ("alpha.example", "Alpha Co", "2026-03-01", now, now),
        )
        conn.execute(
            """
            INSERT INTO contact_candidate
            (contact_email, org_domain, display_name, status, confidence_score, strength_score, evidence_count,
             latest_activity_at, suppression_flags, rationale_text, provenance_json, created_at, updated_at)
            VALUES (?, ?, ?, 'new', 0.3, 0.9, 2, '', '', 'Contact rollup.', '{}', ?, ?)
            """,
            ("person@beta.example", "beta.example", "Person", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_export_filters_entity_kind_and_scores(review_db: Path) -> None:
    conn = connect(review_db)
    try:
        org_only = fetch_queue_rows(
            conn,
            filters=QueueFilters(entity_kind="organization"),
            limit=50,
        )
        assert len(org_only) == 1
        assert org_only[0]["entity_key"] == "alpha.example"

        high_strength = fetch_queue_rows(
            conn,
            filters=QueueFilters(min_strength=0.5),
            limit=50,
        )
        assert len(high_strength) == 1
        assert high_strength[0]["entity_kind"] == "contact"

        high_conf = fetch_queue_rows(
            conn,
            filters=QueueFilters(min_confidence=0.7),
            limit=50,
        )
        assert len(high_conf) == 1
        assert high_conf[0]["entity_kind"] == "organization"

        typed = fetch_queue_rows(
            conn,
            filters=QueueFilters(candidate_type="net_new"),
            limit=50,
        )
        assert len(typed) == 1
        assert typed[0]["candidate_type"] == "net_new"

        csv_out = export_queue_csv(fetch_queue_rows(conn, limit=10))
        assert "reason_summary" in csv_out
        assert "Org rollup summary" in csv_out
    finally:
        conn.close()


def test_review_writes_override_event_and_updates_row(review_db: Path) -> None:
    conn = connect(review_db)
    try:
        r = apply_review_action(
            conn,
            entity_kind="organization",
            entity_key="alpha.example",
            action="reject",
            actor="pytest",
            note="not a fit",
        )
        assert r["previous_status"] == "needs_review"
        assert r["next_status"] == "rejected"
        assert r["review_event_inserted"] == 1

        st = conn.execute(
            "SELECT status FROM organization_candidate WHERE org_domain = ?",
            ("alpha.example",),
        ).fetchone()[0]
        assert st == "rejected"

        ov = conn.execute(
            """
            SELECT override_value, is_active FROM candidate_manual_override
            WHERE entity_kind='organization' AND entity_key='alpha.example' AND override_code='force_status'
            """,
        ).fetchone()
        assert ov == ("rejected", 1)

        ev = conn.execute(
            "SELECT reason_code, note_text, actor FROM candidate_review_event ORDER BY id DESC LIMIT 1",
        ).fetchone()
        assert ev == ("MANUAL_REJECT", "not a fit", "pytest")

        r2 = apply_review_action(
            conn,
            entity_kind="organization",
            entity_key="alpha.example",
            action="approve",
            actor="pytest",
            note="",
        )
        assert r2["review_event_inserted"] == 1
        assert r2["next_status"] == "approved"
    finally:
        conn.close()


def test_review_idempotent_no_event_when_status_unchanged(review_db: Path) -> None:
    conn = connect(review_db)
    try:
        apply_review_action(
            conn,
            entity_kind="organization",
            entity_key="alpha.example",
            action="snooze",
            actor="pytest",
            note="",
        )
        n_before = conn.execute("SELECT COUNT(*) FROM candidate_review_event").fetchone()[0]
        r = apply_review_action(
            conn,
            entity_kind="organization",
            entity_key="alpha.example",
            action="snooze",
            actor="pytest",
            note="again",
        )
        assert r["review_event_inserted"] == 0
        n_after = conn.execute("SELECT COUNT(*) FROM candidate_review_event").fetchone()[0]
        assert n_after == n_before
    finally:
        conn.close()


def test_override_persists_after_builder_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    try:
        migrate_sqlite_schema(
            conn,
            layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL},
        )
        insert_email(
            conn,
            source_file="gmail:contacto@origenlab.cl/INBOX",
            folder="INBOX",
            message_id="<rv1@test>",
            subject="Cotizacion microscopio",
            sender="Lab <compras@labpersist.cl>",
            recipients="contacto@origenlab.cl",
            date_raw="",
            date_iso="2026-03-25T10:00:00Z",
            body="",
            body_html="",
            body_text_raw="Cotizacion microscopio",
            body_text_clean="Cotizacion microscopio",
            body_source_type="plain",
            body_has_plain=True,
            body_has_html=False,
            full_body_clean="Cotizacion microscopio",
            top_reply_clean="Cotizacion microscopio",
            attachment_count=0,
            has_attachments=False,
        )
        insert_email(
            conn,
            source_file="gmail:contacto@origenlab.cl/INBOX",
            folder="INBOX",
            message_id="<rv2@test>",
            subject="Otra cotizacion",
            sender="Lab <compras@labpersist.cl>",
            recipients="contacto@origenlab.cl",
            date_raw="",
            date_iso="2026-03-25T11:00:00Z",
            body="",
            body_html="",
            body_text_raw="Precio microscopio",
            body_text_clean="Precio microscopio",
            body_source_type="plain",
            body_has_plain=True,
            body_has_html=False,
            full_body_clean="Precio microscopio",
            top_reply_clean="Precio microscopio",
            attachment_count=0,
            has_attachments=False,
        )
        conn.commit()
    finally:
        conn.close()

    repo_root = Path(__file__).resolve().parents[1]
    mod = _load_script(
        repo_root / "scripts" / "commercial" / "build_commercial_intel_v1.py",
        "build_commercial_intel_v1_review",
    )
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    monkeypatch.setenv("ORIGENLAB_GMAIL_WORKSPACE_USER", "contacto@origenlab.cl")
    monkeypatch.setattr(mod.sys, "argv", ["build_commercial_intel_v1.py", "--rebuild"])
    assert mod.main() == 0

    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT entity_key FROM v_commercial_candidate_queue WHERE entity_kind='organization' LIMIT 1"
        ).fetchone()
        assert row is not None
        domain = row[0]
        apply_review_action(
            conn,
            entity_kind="organization",
            entity_key=str(domain),
            action="approve",
            actor="pytest",
            note="keep",
        )
    finally:
        conn.close()

    monkeypatch.setattr(mod.sys, "argv", ["build_commercial_intel_v1.py"])
    assert mod.main() == 0

    conn = connect(db)
    try:
        st = conn.execute(
            "SELECT status FROM organization_candidate WHERE org_domain = ?",
            (domain,),
        ).fetchone()[0]
        assert st == "approved"
    finally:
        conn.close()


def test_export_json_roundtrip(review_db: Path, tmp_path: Path) -> None:
    conn = connect(review_db)
    try:
        rows = fetch_queue_rows(conn, limit=5)
    finally:
        conn.close()
    path = tmp_path / "q.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(loaded) == 2
    kinds = {r["entity_kind"] for r in loaded}
    assert kinds == {"organization", "contact"}
