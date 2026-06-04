"""«Qué hacer hoy»: orden, handoff y recolección con fuentes ausentes."""

from __future__ import annotations

import ast
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pytest

from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base, finalize_lead_master_source_keys
from origenlab_email_pipeline.read import today_workspace as tw_mod
from origenlab_email_pipeline.read.leads_browse import lead_browse_ready
from origenlab_email_pipeline.read.today_workspace import (
    SESSION_CI_ENTITY_KIND,
    SESSION_CI_STATUS,
    SESSION_CI_TODAY_HINT,
    SESSION_LEADS_TODAY_BANNER,
    SESSION_OPP_SIGNAL_FILTER,
    SESSION_TODAY_HANDOFF_CASO_EMAIL_ID,
    SOURCE_LABEL_ES,
    TIER_CANDIDATO_NEEDS_REVIEW,
    TIER_CASO_SENAL_POSITIVA,
    TIER_CUENTA_DORMIDA,
    TIER_LABELS_ES,
    TIER_LEAD_SIN_NEXT_ACTION,
    TodayWorkspaceRow,
    TodayWorkspaceSpec,
    apply_today_row_handoff,
    gather_today_workspace_rows,
    sort_today_rows,
    source_label_es,
)

_PKG = Path(__file__).resolve().parents[1] / "src" / "origenlab_email_pipeline"
_TODAY_WORKSPACE_PY = _PKG / "read" / "today_workspace.py"

_EXPECTED_ROW_KEYS = frozenset(
    {
        "tier",
        "tier_label_es",
        "source_code",
        "reason_es",
        "reference_es",
        "next_step_es",
        "navigate_page",
        "sort_primary",
        "sort_secondary",
        "handoff_kind",
        "handoff_email_id",
        "handoff_ci_entity_kind",
        "handoff_ci_entity_key",
        "handoff_lead_id",
        "handoff_lead_org",
    }
)


def _mk_emails(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          date_iso TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          source_file TEXT,
          message_id TEXT,
          top_reply_clean TEXT,
          full_body_clean TEXT,
          body_text_clean TEXT,
          body TEXT
        );
        """
    )


def _mk_commercial_signal_fact(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE commercial_email_signal_fact (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email_id INTEGER NOT NULL,
          source_file TEXT NOT NULL,
          sent_at TEXT,
          sender_email TEXT,
          sender_domain TEXT,
          contact_email TEXT,
          contact_domain TEXT,
          org_domain TEXT,
          signal_code TEXT NOT NULL,
          signal_kind TEXT NOT NULL,
          reason_code TEXT NOT NULL,
          reason_text TEXT NOT NULL,
          confidence_score REAL NOT NULL,
          strength_score REAL NOT NULL,
          rationale_json TEXT NOT NULL,
          run_id INTEGER,
          created_at TEXT NOT NULL,
          UNIQUE(email_id, signal_code, reason_code, contact_email, org_domain)
        );
        """
    )


def _mk_ci_view(conn: sqlite3.Connection, *, entity_key: str = "hospital.cl", confidence: float = 0.9) -> None:
    conn.execute("DROP VIEW IF EXISTS v_commercial_candidate_queue")
    conn.execute(
        f"""
        CREATE VIEW v_commercial_candidate_queue AS
        SELECT
          'organization' AS entity_kind,
          '{entity_key}' AS entity_key,
          'Hospital' AS display_name,
          'Resumen corto' AS reason_summary,
          '' AS rationale_text,
          {confidence} AS confidence_score,
          0.75 AS strength_score,
          'needs_review' AS status,
          '2026-03-01T12:00:00' AS updated_at
        """
    )


def _recent_date_iso(*, days_ago: int = 1) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _insert_lead(
    conn: sqlite3.Connection,
    *,
    lead_id: int,
    org_name: str,
    fit_bucket: str,
    priority_score: float,
    next_action: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name,
          fit_bucket, priority_score, status, next_action,
          first_seen_at, last_seen_at
        ) VALUES (?, 'src', ?, ?, ?, ?, 'nuevo', ?, 't', 't')
        """,
        (lead_id, f"rec-{lead_id}", org_name, fit_bucket, priority_score, next_action),
    )


def _caso_row(tier: int, sp: float, ss: str) -> TodayWorkspaceRow:
    return TodayWorkspaceRow(
        tier=tier,
        tier_label_es="lbl",
        source_code="caso",
        reason_es="r",
        reference_es="ref",
        next_step_es="n",
        navigate_page="Casos para revisar",
        sort_primary=sp,
        sort_secondary=ss,
        handoff_kind="caso",
        handoff_email_id=1,
    )


def test_public_exports_match_all() -> None:
    for name in tw_mod.__all__:
        assert hasattr(tw_mod, name)


def test_session_key_constants_stable() -> None:
    assert SESSION_TODAY_HANDOFF_CASO_EMAIL_ID == "today_handoff_caso_email_id"
    assert SESSION_CI_ENTITY_KIND == "ci_entity_kind"
    assert SESSION_CI_STATUS == "ci_status"
    assert SESSION_CI_TODAY_HINT == "ci_today_hint"
    assert SESSION_LEADS_TODAY_BANNER == "leads_today_banner"
    assert SESSION_OPP_SIGNAL_FILTER == "opp_signal_filter"


def test_tier_labels_and_source_labels_cover_all_tiers() -> None:
    for tier in (
        TIER_CASO_SENAL_POSITIVA,
        TIER_CANDIDATO_NEEDS_REVIEW,
        TIER_LEAD_SIN_NEXT_ACTION,
        TIER_CUENTA_DORMIDA,
    ):
        assert tier in TIER_LABELS_ES
    assert set(SOURCE_LABEL_ES) == {"caso", "candidato", "lead", "oportunidad"}


def test_today_workspace_spec_defaults() -> None:
    sp = TodayWorkspaceSpec()
    assert sp.caso_days_window == 30
    assert sp.caso_positive_limit == 22
    assert sp.candidate_limit == 36
    assert sp.candidate_min_confidence == pytest.approx(0.45)
    assert sp.lead_limit == 32
    assert sp.dormant_limit == 18
    assert sp.max_total_rows == 95
    assert sp.canonical_only is True


def test_row_to_test_dict_shape() -> None:
    row = _caso_row(TIER_CASO_SENAL_POSITIVA, 1.0, "2024-01-01")
    assert frozenset(row.to_test_dict()) == _EXPECTED_ROW_KEYS


def test_today_workspace_source_has_no_streamlit_imports() -> None:
    tree = ast.parse(_TODAY_WORKSPACE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "streamlit" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            assert "streamlit" not in mod


def test_today_workspace_imports_leads_browse_not_streamlit_shim() -> None:
    text = _TODAY_WORKSPACE_PY.read_text(encoding="utf-8")
    assert "read.leads_browse" in text
    assert "streamlit_today_workspace" not in text
    assert "streamlit_leads_browse" not in text


def test_source_label_es_maps_known_codes() -> None:
    assert "Correo" in source_label_es("caso")
    assert source_label_es("desconocido") == "desconocido"


def test_sort_today_rows_tier_then_primary_desc() -> None:
    rows = [
        _caso_row(TIER_CANDIDATO_NEEDS_REVIEW, 1.0, "b"),
        _caso_row(TIER_CASO_SENAL_POSITIVA, 0.5, "a"),
        _caso_row(TIER_CANDIDATO_NEEDS_REVIEW, 3.0, "c"),
    ]
    s = sort_today_rows(rows)
    assert s[0].tier == TIER_CASO_SENAL_POSITIVA
    assert s[1].sort_primary == 3.0
    assert s[2].sort_primary == 1.0


def test_sort_tiebreak_secondary() -> None:
    a = _caso_row(TIER_LEAD_SIN_NEXT_ACTION, 5.0, "2024-02-01")
    b = _caso_row(TIER_LEAD_SIN_NEXT_ACTION, 5.0, "2024-03-01")
    s = sort_today_rows([b, a])
    assert s[0].sort_secondary == "2024-02-01"


def test_apply_handoff_caso() -> None:
    sess: dict[str, object] = {}
    r = TodayWorkspaceRow(
        tier=0,
        tier_label_es="",
        source_code="caso",
        reason_es="",
        reference_es="",
        next_step_es="",
        navigate_page="Casos para revisar",
        sort_primary=0.0,
        sort_secondary="",
        handoff_kind="caso",
        handoff_email_id=42,
    )
    apply_today_row_handoff(r, sess)
    assert sess[SESSION_TODAY_HANDOFF_CASO_EMAIL_ID] == 42
    assert SESSION_TODAY_HANDOFF_CASO_EMAIL_ID == "today_handoff_caso_email_id"


def test_apply_handoff_ci_and_lead() -> None:
    s1: dict[str, object] = {}
    apply_today_row_handoff(
        TodayWorkspaceRow(
            tier=0,
            tier_label_es="",
            source_code="",
            reason_es="",
            reference_es="",
            next_step_es="",
            navigate_page="Candidatos comerciales",
            sort_primary=0.0,
            sort_secondary="",
            handoff_kind="ci",
            handoff_ci_entity_kind="organization",
            handoff_ci_entity_key="x.cl",
        ),
        s1,
    )
    assert s1[SESSION_CI_ENTITY_KIND] == "organization"
    assert s1[SESSION_CI_STATUS] == "needs_review"
    assert s1[SESSION_CI_TODAY_HINT] == "organization | x.cl"

    s2: dict[str, object] = {}
    apply_today_row_handoff(
        TodayWorkspaceRow(
            tier=0,
            tier_label_es="",
            source_code="",
            reason_es="",
            reference_es="",
            next_step_es="",
            navigate_page="Leads y cuentas",
            sort_primary=0.0,
            sort_secondary="",
            handoff_kind="lead",
            handoff_lead_id=7,
            handoff_lead_org="Org",
        ),
        s2,
    )
    assert SESSION_LEADS_TODAY_BANNER in s2
    assert "7" in str(s2[SESSION_LEADS_TODAY_BANNER])

    s3: dict[str, object] = {}
    apply_today_row_handoff(
        TodayWorkspaceRow(
            tier=0,
            tier_label_es="",
            source_code="",
            reason_es="",
            reference_es="",
            next_step_es="",
            navigate_page="Oportunidades",
            sort_primary=0.0,
            sort_secondary="",
            handoff_kind="dormant",
        ),
        s3,
    )
    assert s3[SESSION_OPP_SIGNAL_FILTER] == "dormant_contact"


def test_gather_empty_db() -> None:
    conn = sqlite3.connect(":memory:")
    assert gather_today_workspace_rows(conn) == []


def test_gather_missing_lead_master_skips_lead_tier() -> None:
    conn = sqlite3.connect(":memory:")
    ok, reason = lead_browse_ready(conn)
    assert ok is False
    assert reason == "missing_lead_master"
    assert gather_today_workspace_rows(conn) == []


def test_gather_missing_ci_view_skips_candidato_tier() -> None:
    conn = sqlite3.connect(":memory:")
    _mk_emails(conn)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(1, '2026-03-20', 'H', 'a@b.c', 'gmail:contacto@origenlab.cl/inbox')"
    )
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(max_total_rows=50))
    assert all(r.source_code != "candidato" for r in rows)


def test_gather_caso_tier_positive_signal() -> None:
    conn = sqlite3.connect(":memory:")
    _mk_emails(conn)
    _mk_commercial_signal_fact(conn)
    recent = _recent_date_iso(days_ago=2)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(10, ?, 'Cotización', 'c@x.cl', 'gmail:contacto@origenlab.cl/inbox')",
        (recent,),
    )
    conn.execute(
        """INSERT INTO commercial_email_signal_fact (
          email_id, source_file, signal_code, signal_kind, reason_code, reason_text,
          confidence_score, strength_score, rationale_json, created_at
        ) VALUES (10, 'x', 'q', 'positive', 'r', 't', 0.8, 0.65, '{}', ?)""",
        (f"{recent}T00:00:00Z",),
    )
    conn.commit()
    rows = gather_today_workspace_rows(
        conn, TodayWorkspaceSpec(caso_positive_limit=10, max_total_rows=50)
    )
    caso = [r for r in rows if r.source_code == "caso"]
    assert len(caso) == 1
    assert caso[0].tier == TIER_CASO_SENAL_POSITIVA
    assert caso[0].handoff_kind == "caso"
    assert caso[0].handoff_email_id == 10
    assert caso[0].navigate_page == "Casos para revisar"
    assert caso[0].sort_primary == pytest.approx(0.65)


def test_gather_ci_needs_review_and_skips_noise_entity() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE VIEW v_commercial_candidate_queue AS
        SELECT 'organization' AS entity_kind, 'hospital.cl' AS entity_key,
               'Hospital' AS display_name, 'ok' AS reason_summary, '' AS rationale_text,
               0.9 AS confidence_score, 0.7 AS strength_score,
               'needs_review' AS status, '2026-03-01' AS updated_at
        UNION ALL
        SELECT 'contact', 'mailer-daemon@x.cl', 'Daemon', 'n', '', 0.99, 0.99,
               'needs_review', '2026-03-02'
        """
    )
    conn.commit()
    rows = gather_today_workspace_rows(
        conn,
        TodayWorkspaceSpec(
            candidate_limit=10,
            candidate_min_confidence=0.45,
            canonical_only=True,
            max_total_rows=50,
        ),
    )
    ci = [r for r in rows if r.source_code == "candidato"]
    assert len(ci) == 1
    assert ci[0].tier == TIER_CANDIDATO_NEEDS_REVIEW
    assert ci[0].handoff_ci_entity_key == "hospital.cl"
    assert "mailer-daemon" not in ci[0].reference_es


def test_gather_lead_tier_orders_by_priority_within_tier() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    _insert_lead(conn, lead_id=1, org_name="Low", fit_bucket="high_fit", priority_score=3.0)
    _insert_lead(conn, lead_id=2, org_name="High", fit_bucket="medium_fit", priority_score=9.0)
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(lead_limit=10, max_total_rows=50))
    leads = [r for r in rows if r.source_code == "lead"]
    assert [r.handoff_lead_id for r in leads] == [2, 1]


def test_gather_lead_skips_when_next_action_set() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    _insert_lead(
        conn,
        lead_id=1,
        org_name="Done",
        fit_bucket="high_fit",
        priority_score=5.0,
        next_action="call",
    )
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(lead_limit=10, max_total_rows=50))
    assert not [r for r in rows if r.source_code == "lead"]


def test_gather_mixed_sources_sorted_by_tier_then_truncated() -> None:
    conn = sqlite3.connect(":memory:")
    _mk_emails(conn)
    _mk_commercial_signal_fact(conn)
    recent = _recent_date_iso(days_ago=2)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(10, ?, 'Cot', 'c@x.cl', 'gmail:contacto@origenlab.cl/inbox')",
        (recent,),
    )
    conn.execute(
        """INSERT INTO commercial_email_signal_fact (
          email_id, source_file, signal_code, signal_kind, reason_code, reason_text,
          confidence_score, strength_score, rationale_json, created_at
        ) VALUES (10, 'x', 'q', 'positive', 'r', 't', 0.8, 0.5, '{}', ?)""",
        (recent,),
    )
    _mk_ci_view(conn)
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    _insert_lead(conn, lead_id=1, org_name="L", fit_bucket="high_fit", priority_score=1.0)
    conn.executescript(
        """
        CREATE TABLE contact_master (email TEXT PRIMARY KEY, domain TEXT, last_seen_at TEXT);
        CREATE TABLE organization_master (domain TEXT PRIMARY KEY, last_seen_at TEXT);
        """
    )
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(11, ?, 'Z', 'z@y.cl', 'gmail:contacto@origenlab.cl/inbox')",
        (recent,),
    )
    conn.execute(
        """
        CREATE TABLE opportunity_signals (
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          email_id INTEGER,
          score REAL,
          created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO opportunity_signals VALUES ('dormant_contact','contact','z@y.cl',11,1.0,?)",
        (recent,),
    )
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(max_total_rows=100))
    tiers = [r.tier for r in rows]
    assert tiers == sorted(tiers)
    assert tiers[0] == TIER_CASO_SENAL_POSITIVA
    assert TIER_CUENTA_DORMIDA in tiers
    for row in rows:
        assert frozenset(row.to_test_dict()) == _EXPECTED_ROW_KEYS


def test_gather_dormant_canonical_skipped_when_emails_without_mart_tables() -> None:
    """Characterization: canonical dormant SQL references mart tables; errors are swallowed."""
    conn = sqlite3.connect(":memory:")
    _mk_emails(conn)
    recent = _recent_date_iso(days_ago=1)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(1, ?, 'Z', 'z@y.cl', 'gmail:contacto@origenlab.cl/inbox')",
        (recent,),
    )
    conn.execute(
        """
        CREATE TABLE opportunity_signals (
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          email_id INTEGER,
          score REAL,
          created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO opportunity_signals VALUES ('dormant_contact','contact','z@y.cl',1,9.0,?)",
        (recent,),
    )
    conn.commit()
    rows = gather_today_workspace_rows(
        conn, TodayWorkspaceSpec(dormant_limit=10, canonical_only=True, max_total_rows=50)
    )
    assert not [r for r in rows if r.handoff_kind == "dormant"]


def test_gather_dormant_only() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE opportunity_signals (
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          score REAL,
          created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO opportunity_signals VALUES ('dormant_contact','contact','a@z.cl',99.0,'2024-06-01')",
    )
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(max_total_rows=20))
    assert len(rows) == 1
    assert rows[0].tier == TIER_CUENTA_DORMIDA
    assert rows[0].source_code == "oportunidad"
    d = rows[0].to_test_dict()
    assert d["handoff_kind"] == "dormant"
    assert d["navigate_page"] == "Oportunidades"


def test_gather_leads_tier_without_emails_or_ci() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    _insert_lead(conn, lead_id=1, org_name="Hospital", fit_bucket="high_fit", priority_score=9.0)
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(lead_limit=10, max_total_rows=50))
    assert len(rows) >= 1
    lead_rows = [r for r in rows if r.source_code == "lead"]
    assert len(lead_rows) == 1
    assert lead_rows[0].tier == TIER_LEAD_SIN_NEXT_ACTION
    assert lead_rows[0].handoff_lead_id == 1


def test_max_total_truncates_after_sort() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE opportunity_signals (
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          score REAL,
          created_at TEXT
        )
        """
    )
    for i in range(15):
        conn.execute(
            "INSERT INTO opportunity_signals VALUES ('dormant_contact','contact',?,?,?)",
            (f"u{i}@x.cl", float(i), "2024-01-01"),
        )
    conn.commit()
    rows = gather_today_workspace_rows(conn, TodayWorkspaceSpec(dormant_limit=20, max_total_rows=5))
    assert len(rows) == 5
