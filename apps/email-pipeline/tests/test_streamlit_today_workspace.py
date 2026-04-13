"""«Qué hacer hoy»: orden, handoff y recolección con fuentes ausentes."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.streamlit_prioridad_handoffs import (
    SESSION_CI_ENTITY_KIND,
    SESSION_CI_STATUS,
    SESSION_CI_TODAY_HINT,
    SESSION_LEADS_TODAY_BANNER,
    SESSION_OPP_SIGNAL_FILTER,
    SESSION_TODAY_HANDOFF_CASO_EMAIL_ID,
)
from origenlab_email_pipeline.streamlit_today_workspace import (
    TIER_CANDIDATO_NEEDS_REVIEW,
    TIER_CASO_SENAL_POSITIVA,
    TIER_CUENTA_DORMIDA,
    TIER_LEAD_SIN_NEXT_ACTION,
    TodayWorkspaceRow,
    TodayWorkspaceSpec,
    apply_today_row_handoff,
    gather_today_workspace_rows,
    sort_today_rows,
    source_label_es,
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
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base, finalize_lead_master_source_keys

    conn = sqlite3.connect(":memory:")
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    conn.executescript(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name,
          fit_bucket, priority_score, status, next_action,
          first_seen_at, last_seen_at
        ) VALUES (
          1, 's', 'x', 'Hospital',
          'high_fit', 9.0, 'nuevo', '',
          't', 't'
        );
        """
    )
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
