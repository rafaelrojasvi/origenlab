"""Bloque «Fuente y frescura» compartido por páginas del mart Streamlit."""

from __future__ import annotations

import streamlit as st

PAGE_STATUS_PRESETS: dict[str, dict[str, str]] = {
    "Inicio": {
        "source": "Gmail Workspace **contacto@origenlab.cl** (`gmail:contacto@origenlab.cl/…`) + mart reconstruido",
        "freshness": "Lectura al recargar; KPIs operativos priorizan el buzón canónico",
    },
    "Seguimientos y casos": {
        "source": "Cola **Casos para revisar** (misma SQL: `emails` Gmail contacto)",
        "freshness": "Según ventana de días y filtros en esta página",
    },
    "Contactos y organizaciones": {
        "source": "Tablas `contact_master` / `organization_master` / `document_master` (mart sobre archivo completo)",
        "freshness": "Última reconstrucción del mart; puede incluir histórico no operativo",
    },
    "Outbound / No repetir": {
        "source": "Lectura SQLite + mismas reglas que `check_outbound_readiness` (sin envío)",
        "freshness": "Evaluación al abrir la página",
    },
    "Histórico / Archivo legacy": {
        "source": "Filas `emails` fuera del prefijo Gmail Workspace (p. ej. labdelivery, PST/mbox)",
        "freshness": "Según última importación a este archivo",
    },
    "Herramientas / Runbook": {
        "source": "Sub-vista elegida (cola marketing, borrador, leads, etc.)",
        "freshness": "Varía por herramienta",
    },
    "Resumen": {
        "source": "Archivo histórico + vistas derivadas del mart",
        "freshness": "Mixto: resumen derivado del archivo cargado y del mart reconstruido",
    },
    "Salud de datos": {
        "source": "Archivo histórico y estado técnico de la base actual",
        "freshness": "Según el SQLite abierto y la última reconstrucción disponible",
    },
    "Actividad contacto Gmail": {
        "source": "Gmail contacto",
        "freshness": "Reciente, según correos ya ingestados en esta base",
    },
    "Casos para revisar": {
        "source": "Tabla `emails` filtrada al buzón **Gmail de contacto** (vista de cola, no la bandeja completa).",
        "freshness": "Reciente según `date_iso` y la ventana de días elegida en esta página.",
    },
    "Borrador comercial": {
        "source": "Formulario Streamlit + (opcional) correo elegido en `emails` o metadatos de batch en disco.",
        "freshness": "Mixto: lo que usted escribe ahora; correos según import; batches según carpeta leída del disco.",
    },
    "Cola outreach marketing": {
        "source": "`lead_master` con las mismas reglas de elegibilidad que el export CLI (supresión, Enviados, estados, ruido).",
        "freshness": "Calculado al vuelo al abrir esta página sobre el SQLite abierto (sin envío ni OpenAI aquí).",
    },
    "Qué hacer hoy": {
        "source": "Varias tablas/vistas: correos con CI, candidatos CI, `lead_master`, `opportunity_signals` (cada fila indica su origen).",
        "freshness": "Lectura al recargar; caché corta solo evita releer el mismo archivo si no cambió en disco.",
    },
    "Leads y cuentas": {
        "source": "Leads externos + vínculos con el archivo histórico",
        "freshness": "Mixto: import externo más coincidencias/enriquecimiento sobre la base actual",
    },
    "Proveedores": {
        "source": "Proveedores importados",
        "freshness": "Depende del último workbook importado a esta base",
    },
    "Candidatos comerciales": {
        "source": "Candidatos comerciales",
        "freshness": "Vista derivada del mart y de señales ya construidas",
    },
    "Oportunidades": {
        "source": "Vista derivada del mart",
        "freshness": "Derivada de señales heurísticas reconstruidas",
    },
}


def page_status_values(page_key: str) -> dict[str, str]:
    return dict(PAGE_STATUS_PRESETS.get(page_key) or {})


def render_kpi_metric(label: str, value: str, *, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


def render_page_status(
    page_key: str,
    *,
    note: str | None = None,
    action_hint: str | None = None,
) -> None:
    info = page_status_values(page_key)
    if not info:
        return
    st.markdown("##### Fuente y frescura")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Fuente (SQL / sistema)")
        st.markdown(info.get("source", "—"))
    with c2:
        st.caption("Frescura / actualización")
        st.markdown(info.get("freshness", "—"))
    if action_hint:
        st.caption("Próximo paso sugerido (operador)")
        st.markdown(action_hint)
    if note:
        st.caption(note)


__all__ = [
    "PAGE_STATUS_PRESETS",
    "page_status_values",
    "render_page_status",
    "render_kpi_metric",
]
