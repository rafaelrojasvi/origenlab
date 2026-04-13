"""Texto fijo de ayuda al operador (Prioridad del día): alcance del menú, no reglas SQL."""

from __future__ import annotations

from typing import Any

# Debe coincidir con la etiqueta del grupo en ``business_mart_app._NAV_GROUPS``.
PRIORIDAD_DEL_DIA_GROUP_TITLE = "Prioridad del día"

PRIORIDAD_GROUP_NAV_CAPTION_ES = (
    "**Prioridad del día** no es una cola única: son **cuatro páginas distintas** en el menú, cada una con su propia "
    "consulta y su botón de **siguiente acción**. "
    "**Qué hacer hoy** solo lista atajos: cada fila abre **una** de las otras páginas (Casos, Candidatos, Leads u Oportunidades), "
    "no mezcla colas detrás de escena. "
    "Use **Fuente y frescura** y **Próximo paso sugerido** en cada página para ubicarse."
)

# Una línea corta bajo el subtítulo: a qué página pertenece la vista dentro del grupo.
SCOPE_LINE_BY_PAGE_ES: dict[str, str] = {
    "Qué hacer hoy": "Página del grupo «Prioridad del día» · **resumen** que lista filas de **varias fuentes** (solo lectura).",
    "Casos para revisar": "Página del grupo «Prioridad del día» · cola **Gmail contacto** (tabla `emails`).",
    "Cola outreach marketing": "Página del grupo «Prioridad del día» · cola **`lead_master`** + reglas de export (solo lectura).",
    "Borrador comercial": "Página del grupo «Prioridad del día» · **redacción/revisión** (no envía correos).",
}


def prioridad_scope_caption_for_page(page_key: str) -> str | None:
    """Texto de ámbito para vistas del grupo Prioridad; ``None`` si no aplica."""
    return SCOPE_LINE_BY_PAGE_ES.get(page_key)


# Texto mostrado bajo «Fuente y frescura» (bloque «Próximo paso sugerido») — solo orientación al operador.
PRIORIDAD_ACTION_HINT_BY_PAGE_ES: dict[str, str] = {
    "Qué hacer hoy": (
        "Cada tarjeta es un **atajo de lectura**: pulse el botón para abrir la **página real** del menú donde se revisa "
        "o actúa (Casos, Candidatos comerciales, Leads y cuentas u Oportunidades). Aquí no se editan filas."
    ),
    "Casos para revisar": (
        "**Se revisa en esta página** el correo y el detalle. **Continúa en Borrador comercial** para redactar "
        "(esta cola no envía ni modifica Gmail)."
    ),
    "Cola outreach marketing": (
        "**Se revisa en esta página** la elegibilidad desde `lead_master`. **Continúa en Borrador comercial** "
        "al prellenar el contacto (aquí no hay envío ni OpenAI)."
    ),
    "Borrador comercial": (
        "**Abre Borrador comercial** para generar (si aplica), revisar y **exportar** a disco; el envío lo hace usted "
        "fuera de Streamlit. Si llegó desde **Casos** o **Cola outreach**, el contexto ya viene sugerido."
    ),
}


def prioridad_action_hint_es(page_key: str) -> str | None:
    """Frase de acción sugerida por página del grupo Prioridad (para ``render_page_status``)."""
    return PRIORIDAD_ACTION_HINT_BY_PAGE_ES.get(page_key)


def prioridad_hoy_vs_casos_diff_es() -> str:
    """Mensaje corto para evitar confusión entre «Qué hacer hoy» y «Casos para revisar»."""
    return (
        "**Qué hacer hoy** es un tablero de sugerencias multi-fuente (atajos). "
        "**Casos para revisar** es una cola específica de correos de **Gmail contacto**."
    )


def today_row_operational_destination_es(navigate_page: str) -> str:
    """Una línea: en qué página del menú continúa la fila (valores de ``TodayWorkspaceRow.navigate_page``)."""
    fixed: dict[str, str] = {
        "Casos para revisar": "**Página operativa:** Casos para revisar — se revisa el hilo allí; el borrador es en otra vista.",
        "Candidatos comerciales": "**Página operativa:** Candidatos comerciales — profundizar y aplicar la acción CI allí.",
        "Leads y cuentas": "**Página operativa:** Leads y cuentas — profundizar en el lead y el import allí.",
        "Oportunidades": "**Página operativa:** Oportunidades — profundizar en señales del mart (p. ej. cuenta dormida) allí.",
    }
    return fixed.get(navigate_page, f"**Página operativa:** {navigate_page} — vista del menú lateral.")


def today_row_visibility_hint_es(source_code: str, navigate_page: str) -> str:
    """Línea de procedencia/estado por tarjeta de «Qué hacer hoy» (solo lectura)."""
    hints: dict[str, str] = {
        "caso": "Visible aquí por señal comercial positiva sobre un correo de Gmail contacto.",
        "candidato": "Visible aquí por estado `needs_review` en la cola de candidatos CI.",
        "lead": "Visible aquí por encaje high/medium sin `next_action` en `lead_master`.",
        "oportunidad": "Visible aquí por señal `dormant_contact` en `opportunity_signals`.",
    }
    base = hints.get(source_code, "Visible aquí por criterios de la cola de origen.")
    return f"{base} Continúa en **{navigate_page}**."


def today_row_nav_button_label_es(navigate_page: str) -> str:
    """Etiqueta visible del botón de navegación desde «Qué hacer hoy» (mismo destino que antes)."""
    labels: dict[str, str] = {
        "Casos para revisar": "Abrir Casos para revisar",
        "Candidatos comerciales": "Abrir Candidatos comerciales",
        "Leads y cuentas": "Abrir Leads y cuentas",
        "Oportunidades": "Abrir Oportunidades",
    }
    return labels.get(navigate_page, "Abrir la página destino")


def cases_row_visibility_badges_es(row: dict[str, Any], *, enrichment_available: bool) -> list[str]:
    """Badges de estado visibles para una fila de Casos (sin recalcular reglas)."""
    out: list[str] = ["familia=emails(Gmail contacto)"]
    if enrichment_available:
        if int(row.get("has_positive_signal") or 0) == 1:
            out.append("ci=positiva")
        elif row.get("has_positive_signal") is not None:
            out.append("ci=sin_positiva")
        if int(row.get("has_suppression_signal") or 0) == 1:
            out.append("ruido/supresión=posible")
        mx = row.get("max_positive_strength")
        if mx is not None:
            try:
                out.append(f"intensidad+={float(mx):.2f}")
            except (TypeError, ValueError):
                pass
    else:
        out.append("ci=tabla_no_disponible")
    return out


def marketing_row_visibility_badges_es(row: dict[str, Any]) -> list[str]:
    """Badges de contexto para fila ya elegible de Cola outreach marketing."""
    out = ["familia=lead_master"]
    fit = str(row.get("fit_bucket") or "").strip()
    if fit:
        out.append(f"fit={fit}")
    if int(row.get("already_in_archive_flag") or 0) == 1:
        out.append("archivo=ya_relacionado")
    else:
        out.append("archivo=no_relacionado")
    src = str(row.get("source_name") or "").strip()
    if src:
        out.append(f"fuente={src}")
    return out


def borrador_visibility_origin_es(*, mode: str, manual_kind: str | None) -> str:
    """Resumen de origen operativo para la pantalla Borrador (solo copy)."""
    if mode == "Correo reciente (Gmail contacto)":
        return "Origen activo: correo de **Gmail contacto** (flujo típico desde Casos para revisar)."
    if manual_kind == "Outreach / presentacion comercial":
        return "Origen activo: **outreach manual** (flujo típico desde Cola outreach marketing o entrada directa)."
    return "Origen activo: entrada manual de caso puntual (no depende de una cola automática)."


__all__ = [
    "PRIORIDAD_DEL_DIA_GROUP_TITLE",
    "PRIORIDAD_GROUP_NAV_CAPTION_ES",
    "PRIORIDAD_ACTION_HINT_BY_PAGE_ES",
    "SCOPE_LINE_BY_PAGE_ES",
    "prioridad_scope_caption_for_page",
    "prioridad_action_hint_es",
    "prioridad_hoy_vs_casos_diff_es",
    "today_row_operational_destination_es",
    "today_row_visibility_hint_es",
    "today_row_nav_button_label_es",
    "cases_row_visibility_badges_es",
    "marketing_row_visibility_badges_es",
    "borrador_visibility_origin_es",
]
