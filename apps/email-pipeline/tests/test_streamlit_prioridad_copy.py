from __future__ import annotations

from origenlab_email_pipeline.streamlit_prioridad_copy import (
    PRIORIDAD_DEL_DIA_GROUP_TITLE,
    PRIORIDAD_GROUP_NAV_CAPTION_ES,
    borrador_visibility_origin_es,
    cases_row_visibility_badges_es,
    marketing_row_visibility_badges_es,
    prioridad_action_hint_es,
    prioridad_hoy_vs_casos_diff_es,
    prioridad_scope_caption_for_page,
    today_row_nav_button_label_es,
    today_row_operational_destination_es,
    today_row_visibility_hint_es,
)


def test_prioridad_group_title_matches_nav_contract() -> None:
    assert PRIORIDAD_DEL_DIA_GROUP_TITLE == "Prioridad del día"


def test_nav_caption_mentions_four_views_not_single_queue() -> None:
    low = PRIORIDAD_GROUP_NAV_CAPTION_ES.lower()
    assert "cuatro" in low and "páginas" in low
    assert "no es una cola única" in low
    assert "qué hacer hoy" in low
    assert "próximo paso sugerido" in low


def test_scope_lines_exist_for_each_prioridad_page() -> None:
    for page in (
        "Qué hacer hoy",
        "Casos para revisar",
        "Cola outreach marketing",
        "Borrador comercial",
    ):
        cap = prioridad_scope_caption_for_page(page)
        assert cap
        assert "Prioridad del día" in cap


def test_prioridad_action_hint_covers_all_four_pages() -> None:
    for page in (
        "Qué hacer hoy",
        "Casos para revisar",
        "Cola outreach marketing",
        "Borrador comercial",
    ):
        h = prioridad_action_hint_es(page)
        assert h
        assert len(h) > 40


def test_hoy_vs_casos_diff_copy_mentions_scope() -> None:
    s = prioridad_hoy_vs_casos_diff_es()
    assert "multi-fuente" in s
    assert "Gmail contacto" in s


def test_today_row_operational_destination_known_pages() -> None:
    assert "Casos para revisar" in today_row_operational_destination_es("Casos para revisar")
    assert "Candidatos comerciales" in today_row_operational_destination_es("Candidatos comerciales")
    assert "Leads y cuentas" in today_row_operational_destination_es("Leads y cuentas")
    assert "Oportunidades" in today_row_operational_destination_es("Oportunidades")


def test_today_row_operational_destination_unknown_falls_back() -> None:
    s = today_row_operational_destination_es("Otra página")
    assert "Otra página" in s


def test_today_row_nav_button_labels_match_menu_pages() -> None:
    assert today_row_nav_button_label_es("Casos para revisar") == "Abrir Seguimientos y casos"
    assert today_row_nav_button_label_es("Candidatos comerciales") == "Abrir Candidatos comerciales (Herramientas)"
    assert today_row_nav_button_label_es("Leads y cuentas") == "Abrir Leads y cuentas (Herramientas)"
    assert today_row_nav_button_label_es("Oportunidades") == "Abrir Oportunidades"
    assert "destino" in today_row_nav_button_label_es("desconocido").lower()


def test_today_row_visibility_hint_mentions_destination() -> None:
    s = today_row_visibility_hint_es("caso", "Casos para revisar")
    assert "Gmail contacto" in s
    assert "Casos para revisar" in s


def test_cases_row_visibility_badges_with_enrichment() -> None:
    badges = cases_row_visibility_badges_es(
        {
            "has_positive_signal": 1,
            "has_suppression_signal": 1,
            "max_positive_strength": 0.73,
        },
        enrichment_available=True,
    )
    joined = " ".join(badges)
    assert "familia=emails" in joined
    assert "ci=positiva" in joined
    assert "supresión" in joined
    assert "0.73" in joined


def test_marketing_row_visibility_badges_include_fit_and_source() -> None:
    badges = marketing_row_visibility_badges_es(
        {
            "fit_bucket": "high_fit",
            "already_in_archive_flag": 0,
            "source_name": "portal_x",
        }
    )
    joined = " ".join(badges)
    assert "lead_master" in joined
    assert "fit=high_fit" in joined
    assert "portal_x" in joined


def test_borrador_visibility_origin_by_mode() -> None:
    assert "Gmail contacto" in borrador_visibility_origin_es(mode="Correo reciente (Gmail contacto)", manual_kind=None)
    assert "outreach manual" in borrador_visibility_origin_es(
        mode="Entrada manual",
        manual_kind="Outreach / presentacion comercial",
    )
