from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from origenlab_email_pipeline.config import load_settings


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    # Use immutable=1 so SQLite won't try to create -wal/-shm files.
    # This is important when the DB is volume-mounted read-only in Docker.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _load_df(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


BRAND = {
    "50": "#f0fdfa",
    "500": "#14b8a6",
    "600": "#0d9488",
    "700": "#0f766e",
    "800": "#115e59",
    "900": "#134e4a",
    "950": "#042f2e",
}


def _kpi(label: str, value: str, *, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


EQUIPMENT_INFO: dict[str, dict[str, str]] = {
    "autoclave": {
        "label": "Autoclave",
        "description": "Equipo de esterilización por vapor a alta presión y temperatura para material de laboratorio y residuos biológicos.",
    },
    "balanza": {
        "label": "Balanza",
        "description": "Equipo para pesar muestras con precisión (analítica, semi-micro, etc.).",
    },
    "osmometro": {
        "label": "Osmómetro",
        "description": "Equipo para medir la osmolaridad/osmolalidad de soluciones o muestras biológicas y de laboratorio.",
    },
    "termobalanza": {
        "label": "Termobalanza",
        "description": "Equipo termoanalítico para determinaciones por pérdida de masa/variación con temperatura (p. ej., TGA/termo-gravimetría).",
    },
    "centrifuga": {
        "label": "Centrífuga",
        "description": "Equipo que separa componentes de una muestra por fuerza centrífuga (rpm / RCF).",
    },
    "cromatografia_hplc": {
        "label": "Cromatografía HPLC",
        "description": "Sistema de cromatografía líquida de alta resolución para análisis cuantitativo de compuestos.",
    },
    "espectrofotometro": {
        "label": "Espectrofotómetro",
        "description": "Equipo que mide absorbancia/transmitancia de luz a distintas longitudes de onda.",
    },
    "horno_mufla": {
        "label": "Horno mufla",
        "description": "Horno de alta temperatura para calcinación, pérdida por ignición y otros ensayos térmicos.",
    },
    "humedad_granos": {
        "label": "Medidor de humedad",
        "description": "Equipo para determinar el porcentaje de humedad en granos y otros materiales (según el contexto del texto).",
    },
    "incubadora": {
        "label": "Incubadora",
        "description": "Cámara controlada de temperatura (y a veces CO₂/humedad) para cultivo de microorganismos y células.",
    },
    "liofilizador": {
        "label": "Liofilizador",
        "description": "Equipo para secado por congelación (freeze-drying) de muestras sensibles.",
    },
    "microscopio": {
        "label": "Microscopio",
        "description": "Equipo óptico para observación ampliada de muestras (biológicas o materiales).",
    },
    "phmetro": {
        "label": "pH-metro",
        "description": "Instrumento para medir de forma precisa el pH de soluciones acuosas.",
    },
    "pipetas": {
        "label": "Pipetas",
        "description": "Pipetas y micropipetas para dispensar volúmenes conocidos de líquido con precisión.",
    },
    "titulador": {
        "label": "Titulador",
        "description": "Equipo (manual o automático) para realizar titulaciones y determinar concentraciones de analitos.",
    },
    "sonicador": {
        "label": "Sonicador / ultrasonido",
        "description": "Equipo de ultrasonido para dispersar muestras, romper células o limpiar piezas por cavitación.",
    },
}


def _navigate_to(page: str, **flags: object) -> None:
    """Actualizar session_state para navegación guiada y forzar recarga ligera."""
    st.session_state["start_page"] = page
    for k, v in flags.items():
        st.session_state[k] = v
    # En Streamlit moderno, st.rerun() es la forma soportada.
    try:
        st.rerun()
    except AttributeError:
        # Compatibilidad defensiva con versiones antiguas.
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()


def _friendly_org_type(code: str | None) -> str:
    if not code:
        return "Sin clasificar"
    mapping = {
        "education": "Educación (universidad/centro académico)",
        "business": "Empresa",
        "gov": "Gobierno",
        "personal": "Email personal / otro",
    }
    return mapping.get(code, "Otro tipo de organización")


def _friendly_doc_type(code: str | None) -> str:
    if not code:
        return "Documento sin clasificar"
    mapping = {
        "quote": "Cotización",
        "invoice": "Factura",
        "price_list": "Lista de precios",
        "purchase_order": "Orden de compra",
    }
    return mapping.get(code, "Otro documento")


def _signal_label(signal_type: str) -> tuple[str, str]:
    m = {
        "quote_email_plus_quote_doc": (
            "Cotización + documento",
            "Contacto con correos de cotización repetidos y al menos un documento tipo cotización extraído.",
        ),
        "education_with_quote_activity": (
            "Universidad con cotización",
            "Organización tipo educación con actividad de cotización (correo o documento).",
        ),
        "dormant_contact": (
            "Cuenta dormida",
            "Contacto con alto historial, pero sin actividad reciente (heurístico).",
        ),
        "repeated_equipment_theme": (
            "Tema de equipo recurrente",
            "Contacto que menciona repetidamente el mismo equipo (tag) en asunto/cuerpo/documentos.",
        ),
    }
    return m.get(signal_type, (signal_type, "Señal heurística (ver detalles)."))


def _split_tags(value: object) -> list[str]:
    """Dividir un campo de tags heurísticos en una lista normalizada."""
    if value is None:
        return []
    text = str(value)
    if not text.strip():
        return []
    # Unificamos separadores comunes (coma / punto y coma / barra vertical).
    cleaned = text.replace(";", ",").replace("|", ",")
    tags: list[str] = []
    for raw in cleaned.split(","):
        t = raw.strip()
        if not t:
            continue
        # Normalización ligera de sinónimos, en particular ultrasonido → sonicador.
        low = t.lower()
        if "ultrason" in low or "ultra sonido" in low or "ultrasónico" in low or "ultrasonico" in low:
            tags.append("sonicador")
        else:
            tags.append(t)
    return tags


def _normalize_query(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _consume_nav_flag(key: str, default: bool = False) -> bool:
    """Consume one-shot navigation flags so quick-actions do not stick forever."""
    if key in st.session_state:
        return bool(st.session_state.pop(key))
    return default


def _search_relevance_score(df: pd.DataFrame, query: str, columns: list[str]) -> pd.Series:
    q = _normalize_query(query)
    if not q or df.empty:
        return pd.Series([0.0] * len(df), index=df.index)

    score = pd.Series([0.0] * len(df), index=df.index)
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].fillna("").astype(str).str.lower()
        score += s.eq(q).astype(float) * 120.0
        score += s.str.startswith(q, na=False).astype(float) * 80.0
        score += s.str.contains(q, na=False).astype(float) * 30.0

    # Bonus when all tokens appear somewhere in searchable text.
    searchable = pd.Series([""] * len(df), index=df.index)
    for col in columns:
        if col in df.columns:
            searchable = searchable + " " + df[col].fillna("").astype(str).str.lower()
    for tok in [t for t in q.split(" ") if t]:
        score += searchable.str.contains(tok, na=False).astype(float) * 8.0
    return score


def _render_equipment_page(conn: sqlite3.Connection) -> None:
    """Dedicated equipment explorer (moved out of executive summary)."""
    st.subheader("Explorar por equipo")
    st.caption(
        "Seleccione un tipo de equipo para ver organizaciones, contactos, documentos y señales históricas "
        "relacionadas con ese tema."
    )

    tags: set[str] = set()
    org_tags_df = _load_df(
        conn,
        "SELECT DISTINCT top_equipment_tags FROM organization_master WHERE top_equipment_tags IS NOT NULL",
    )
    contact_tags_df = _load_df(
        conn,
        "SELECT DISTINCT top_equipment_tags FROM contact_master WHERE top_equipment_tags IS NOT NULL",
    )
    doc_tags_df = _load_df(
        conn,
        "SELECT DISTINCT equipment_tags FROM document_master WHERE equipment_tags IS NOT NULL",
    )
    for df_tags in (org_tags_df, contact_tags_df, doc_tags_df):
        for val in df_tags.iloc[:, 0].dropna():
            for t in _split_tags(val):
                tags.add(t)

    if not tags:
        st.info(
            "Por ahora no se detectan tags de equipos en el mart actual. "
            "Cuando existan, aquí se podrá explorar por equipo."
        )
        return

    preferred_order = [
        "autoclave",
        "balanza",
        "termobalanza",
        "osmometro",
        "centrifuga",
        "cromatografia_hplc",
        "espectrofotometro",
        "horno_mufla",
        "humedad_granos",
        "incubadora",
        "liofilizador",
        "microscopio",
        "phmetro",
        "pipetas",
        "titulador",
        "sonicador",
    ]
    preferred_in_data = [t for t in preferred_order if t in tags]
    remaining = sorted([t for t in tags if t not in preferred_in_data], key=lambda x: x.lower())
    ordered_tags = preferred_in_data + remaining

    display_to_tag: dict[str, str] = {}
    display_options: list[str] = []
    for tag in ordered_tags:
        info = EQUIPMENT_INFO.get(tag, {})
        label = info.get("label", tag)
        display = f"{label} ({tag})" if label != tag else label
        display_to_tag[display] = tag
        display_options.append(display)

    selected_display = st.selectbox("Seleccionar equipo o tema", options=display_options)
    selected_tag = display_to_tag[selected_display] if selected_display else ""
    if not selected_tag:
        return

    info = EQUIPMENT_INFO.get(selected_tag, {})
    label = info.get("label", selected_tag)
    st.markdown(f"Mostrando actividad histórica relacionada con **{label}**.")
    if desc := info.get("description"):
        st.caption(desc)

    st.markdown("#### Organizaciones relacionadas con este equipo")
    org_eq = _load_df(
        conn,
        """
        SELECT
          domain AS dominio,
          organization_name_guess AS organizacion,
          organization_type_guess AS tipo_org,
          first_seen_at AS primera,
          last_seen_at AS ultima,
          total_emails AS total,
          quote_email_count AS cotiz_email,
          invoice_email_count AS factura_email,
          purchase_email_count AS compra_email,
          business_doc_email_count AS doc_emails,
          top_equipment_tags AS equipos
        FROM organization_master
        """,
    )
    mask_org_eq = org_eq["equipos"].fillna("").str.contains(selected_tag, case=False, na=False)
    org_eq = org_eq[mask_org_eq]
    if org_eq.empty:
        st.info("No se encontraron organizaciones claramente asociadas a este equipo.")
    else:
        org_eq_display = org_eq.copy()
        org_eq_display["tipo_org"] = org_eq_display["tipo_org"].apply(
            lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
        )
        org_eq_display = org_eq_display.rename(
            columns={
                "dominio": "Dominio",
                "organizacion": "Organización",
                "tipo_org": "Tipo de organización",
                "primera": "Primera actividad",
                "ultima": "Última actividad",
                "total": "Total de correos",
                "cotiz_email": "Correos con cotización",
                "factura_email": "Correos con factura",
                "compra_email": "Correos de compra/pedido",
                "doc_emails": "Correos con documentos comerciales",
                "equipos": "Equipos asociados (heurístico)",
            }
        )
        st.dataframe(org_eq_display.head(50), use_container_width=True, hide_index=True)

    st.markdown("#### Contactos relacionados con este equipo")
    contact_eq = _load_df(
        conn,
        """
        SELECT
          email,
          domain AS dominio,
          organization_name_guess AS organizacion,
          organization_type_guess AS tipo_org,
          first_seen_at AS primera,
          last_seen_at AS ultima,
          total_emails AS total,
          quote_email_count AS cotiz_email,
          invoice_email_count AS factura_email,
          business_doc_email_count AS doc_emails,
          top_equipment_tags AS equipos
        FROM contact_master
        """,
    )
    mask_contact_eq = contact_eq["equipos"].fillna("").str.contains(selected_tag, case=False, na=False)
    contact_eq = contact_eq[mask_contact_eq]
    if contact_eq.empty:
        st.info("No se encontraron contactos claramente asociados a este equipo.")
    else:
        contact_eq_display = contact_eq.copy()
        contact_eq_display["tipo_org"] = contact_eq_display["tipo_org"].apply(
            lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
        )
        contact_eq_display = contact_eq_display.rename(
            columns={
                "email": "Contacto (email)",
                "dominio": "Dominio",
                "organizacion": "Organización",
                "tipo_org": "Tipo de organización",
                "primera": "Primera actividad",
                "ultima": "Última actividad",
                "total": "Total de correos",
                "cotiz_email": "Correos con cotización",
                "factura_email": "Correos con factura",
                "doc_emails": "Correos con documentos comerciales",
                "equipos": "Equipos asociados (heurístico)",
            }
        )
        st.dataframe(contact_eq_display.head(80), use_container_width=True, hide_index=True)

    st.markdown("#### Documentos comerciales relacionados con este equipo")
    doc_eq = _load_df(
        conn,
        """
        SELECT
          attachment_id,
          sent_at,
          doc_type,
          filename,
          sender_domain,
          equipment_tags
        FROM document_master
        """,
    )
    mask_doc_eq = doc_eq["equipment_tags"].fillna("").str.contains(selected_tag, case=False, na=False)
    doc_eq = doc_eq[mask_doc_eq]
    if doc_eq.empty:
        st.info("No se encontraron documentos explícitamente asociados a este equipo.")
    else:
        doc_eq_display = doc_eq.copy()
        doc_eq_display["doc_type"] = doc_eq_display["doc_type"].apply(
            lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
        )
        doc_eq_display = doc_eq_display.rename(
            columns={
                "sent_at": "Fecha envío",
                "doc_type": "Tipo de documento",
                "filename": "Archivo",
                "sender_domain": "Dominio remitente",
                "equipment_tags": "Equipos mencionados",
            }
        )
        st.dataframe(doc_eq_display.head(80), use_container_width=True, hide_index=True)

    st.markdown("#### Señales heurísticas relacionadas con este equipo")
    signals_eq = _load_df(
        conn,
        """
        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
        FROM opportunity_signals
        WHERE details_json LIKE ?
        ORDER BY score DESC, created_at DESC
        """,
        (f"%{selected_tag}%",),
    )
    if signals_eq.empty:
        st.info(
            "No se encontraron señales heurísticas donde el detalle haga referencia explícita a este equipo."
        )
    else:
        signals_eq["señal"] = signals_eq["signal_type"].apply(lambda x: _signal_label(str(x))[0])
        signals_eq["explicación"] = signals_eq["signal_type"].apply(lambda x: _signal_label(str(x))[1])
        signals_display = signals_eq[
            ["señal", "explicación", "entity_kind", "entity_key", "score", "created_at"]
        ].copy()
        signals_display["Entidad"] = signals_display["entity_kind"].map(
            {"contact": "Contacto", "organization": "Organización"}
        ).fillna(signals_display["entity_kind"])
        signals_display = signals_display.rename(
            columns={
                "entity_key": "Clave (email/dominio)",
                "score": "Intensidad de la señal",
                "created_at": "Detectado el",
            }
        ).drop(columns=["entity_kind"])
        st.dataframe(signals_display.head(80), use_container_width=True, hide_index=True)
        with st.expander("Ver detalles técnicos de las señales por equipo"):
            st.dataframe(
                signals_eq[
                    ["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]
                ].head(200),
                use_container_width=True,
                hide_index=True,
            )


def main() -> None:
    st.set_page_config(page_title="OrigenLab — Base Comercial", layout="wide")
    st.title("OrigenLab — Base comercial")
    st.caption(
        "Señales y actividad histórica en correo/adjuntos. No implica ventas confirmadas ni facturación real."
    )

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()

    with st.expander("Fuente de datos (técnico)"):
        st.code(str(db_path))

    conn = _connect_ro(db_path)
    try:
        required = ["contact_master", "organization_master", "document_master", "opportunity_signals"]
        missing = [t for t in required if not _has_table(conn, t)]
        if missing:
            st.error("Faltan tablas del mart: " + ", ".join(missing))
            st.info("Ejecute primero: `uv run python scripts/mart/build_business_mart.py --rebuild`")
            return

        # Navegación principal: permitir que quick-actions cambien de pestaña.
        if "start_page" in st.session_state:
            default_page = st.session_state.pop("start_page")
        else:
            default_page = "Resumen"

        pages = ["Resumen", "Oportunidades", "Equipos", "Organizaciones", "Contactos", "Documentos"]
        if default_page not in pages:
            default_page = "Resumen"

        page = st.radio(
            "Sección",
            pages,
            horizontal=True,
            label_visibility="collapsed",
            index=pages.index(default_page),
        )

        if page == "Resumen":
            st.subheader("Resumen ejecutivo")
            total_msgs = int(_load_df(conn, "SELECT COUNT(*) AS c FROM emails").iloc[0]["c"])
            contacts_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM contact_master").iloc[0]["c"])
            orgs_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM organization_master").iloc[0]["c"])
            docs_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM document_master").iloc[0]["c"])
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                _kpi("Mensajes analizados", f"{total_msgs:,}")
            with c2:
                _kpi("Contactos externos", f"{contacts_n:,}")
            with c3:
                _kpi("Organizaciones externas", f"{orgs_n:,}")
            with c4:
                _kpi("Documentos útiles", f"{docs_n:,}")

            # Periodo aproximado de cobertura del archivo de correo.
            try:
                period_df = _load_df(
                    conn,
                    "SELECT MIN(date_iso) AS primera, MAX(date_iso) AS ultima FROM emails WHERE date_iso IS NOT NULL",
                )
                primera = period_df.iloc[0]["primera"]
                ultima = period_df.iloc[0]["ultima"]
                if pd.notna(primera) and pd.notna(ultima):
                    primera_y = str(primera)[:4]
                    ultima_y = str(ultima)[:4]
                    st.caption(f"Periodo aproximado cubierto por el archivo: {primera_y}–{ultima_y}.")
            except Exception:
                # Si falla, no obstaculiza la navegación.
                pass

            st.markdown(
                "Esta base actúa como **memoria comercial histórica** basada en correos y adjuntos. "
                "No representa ventas confirmadas, sino señales e indicios de interés comercial."
            )

            st.divider()
            st.markdown("### Preguntas rápidas")
            qa_row1 = st.columns(3)

            with qa_row1[0]:
                st.markdown("**Universidades con cotización**")
                st.caption("Ver universidades con actividad de correos o documentos de cotización.")
                if st.button("Ir a organizaciones (universidades)", key="qa_unis_quotes"):
                    _navigate_to("Organizaciones", org_only_unis=True)

            with qa_row1[1]:
                st.markdown("**Clientes con muchas cotizaciones**")
                st.caption("Organizaciones con alto volumen de correos y documentos de cotización.")
                if st.button("Ver organizaciones con cotización", key="qa_org_quotes"):
                    _navigate_to("Organizaciones", org_focus_quotes=True)

            with qa_row1[2]:
                st.markdown("**Proveedores con facturas**")
                st.caption("Organizaciones con correos o documentos detectados como factura.")
                if st.button("Ver organizaciones con facturas", key="qa_org_invoices"):
                    _navigate_to("Organizaciones", org_only_invoices=True)

            qa_row2 = st.columns(3)

            with qa_row2[0]:
                st.markdown("**Cuentas dormidas valiosas**")
                st.caption("Contactos con mucho historial pero sin actividad reciente.")
                if st.button("Ver oportunidades de cuentas dormidas", key="qa_dormant_contacts"):
                    _navigate_to("Oportunidades", opp_signal_filter="dormant_contact")

            with qa_row2[1]:
                st.markdown("**Documentos de cotización recientes**")
                st.caption("Adjuntos clasificados como cotización en los últimos años.")
                if st.button("Ver documentos de cotización", key="qa_quote_docs"):
                    _navigate_to("Documentos", docs_only_quotes=True)

            with qa_row2[2]:
                st.markdown("**Universidades con facturación**")
                st.caption("Universidades donde se detectaron facturas o documentos similares.")
                if st.button("Ver universidades con facturas", key="qa_unis_invoices"):
                    _navigate_to("Organizaciones", org_only_unis_invoices=True)

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Universidades con actividad de cotización**")
                uni = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      quote_doc_count AS cotiz_docs
                    FROM organization_master
                    WHERE organization_type_guess='education'
                      AND (quote_email_count > 0 OR quote_doc_count > 0)
                    ORDER BY (quote_email_count + quote_doc_count) DESC, total_emails DESC
                    LIMIT 12
                    """,
                )
                if uni.empty:
                    st.info("No se detectó actividad de cotización en organizaciones tipo educación.")
                else:
                    st.dataframe(uni, use_container_width=True, hide_index=True)

            with c2:
                st.markdown("**Organizaciones con actividad de factura**")
                inv = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      invoice_email_count AS factura_email,
                      invoice_doc_count AS factura_docs
                    FROM organization_master
                    WHERE invoice_email_count > 0 OR invoice_doc_count > 0
                    ORDER BY (invoice_email_count + invoice_doc_count) DESC, total_emails DESC
                    LIMIT 12
                    """,
                )
                if inv.empty:
                    st.info("No se detectó actividad de factura en el mart actual.")
                else:
                    st.dataframe(inv, use_container_width=True, hide_index=True)

            with st.expander("Informe estático (HTML)"):
                st.markdown(
                    "La versión estática completa del informe se encuentra en el entorno de análisis en:\n\n"
                    "`reports/out/20260317_162013/index.html`\n\n"
                    "Esta app muestra una vista dinámica del mismo mart; "
                    "el informe HTML sigue siendo la referencia narrativa detallada."
                )

            # Radar de cotizaciones: organizaciones, contactos y cuentas dormidas.
            st.divider()
            st.markdown("### Radar de cotizaciones")
            st.caption(
                "Vista rápida de organizaciones y contactos con **alta actividad histórica de cotización**. "
                "Incluye correos donde se habla de cotizar y documentos detectados como cotización."
            )

            col_orgs, col_contacts = st.columns(2)

            with col_orgs:
                st.markdown("#### Organizaciones con mayor actividad de cotización")
                radar_orgs = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      organization_type_guess AS tipo_org,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      quote_doc_count AS cotiz_docs,
                      business_doc_email_count AS doc_emails,
                      top_equipment_tags AS equipos
                    FROM organization_master
                    WHERE quote_email_count > 0 OR quote_doc_count > 0
                    ORDER BY (quote_email_count + quote_doc_count) DESC, total_emails DESC
                    LIMIT 15
                    """,
                )
                if radar_orgs.empty:
                    st.info("No se encontraron organizaciones con actividad clara de cotización.")
                else:
                    radar_orgs_display = radar_orgs.copy()
                    radar_orgs_display["tipo_org"] = radar_orgs_display["tipo_org"].apply(
                        lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                    )
                    radar_orgs_display = radar_orgs_display.rename(
                        columns={
                            "dominio": "Dominio",
                            "organizacion": "Organización",
                            "tipo_org": "Tipo de organización",
                            "primera": "Primera actividad",
                            "ultima": "Última actividad",
                            "total": "Total de correos",
                            "cotiz_email": "Correos con cotización",
                            "cotiz_docs": "Documentos de cotización",
                            "doc_emails": "Correos con documentos comerciales",
                            "equipos": "Equipos asociados (heurístico)",
                        }
                    )
                    st.dataframe(radar_orgs_display, use_container_width=True, hide_index=True)

            with col_contacts:
                st.markdown("#### Contactos con mayor actividad de cotización")
                radar_contacts = _load_df(
                    conn,
                    """
                    SELECT
                      email,
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      organization_type_guess AS tipo_org,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      business_doc_email_count AS doc_emails,
                      top_equipment_tags AS equipos
                    FROM contact_master
                    WHERE quote_email_count > 0
                    ORDER BY quote_email_count DESC, total_emails DESC
                    LIMIT 15
                    """,
                )
                if radar_contacts.empty:
                    st.info("No se encontraron contactos con actividad clara de cotización.")
                else:
                    radar_contacts_display = radar_contacts.copy()
                    radar_contacts_display["tipo_org"] = radar_contacts_display["tipo_org"].apply(
                        lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                    )
                    radar_contacts_display = radar_contacts_display.rename(
                        columns={
                            "email": "Contacto (email)",
                            "dominio": "Dominio",
                            "organizacion": "Organización",
                            "tipo_org": "Tipo de organización",
                            "primera": "Primera actividad",
                            "ultima": "Última actividad",
                            "total": "Total de correos",
                            "cotiz_email": "Correos con cotización",
                            "doc_emails": "Correos con documentos comerciales",
                            "equipos": "Equipos asociados (heurístico)",
                        }
                    )
                    st.dataframe(radar_contacts_display, use_container_width=True, hide_index=True)

            # Cuentas dormidas con historial de cotización (basado en señales heurísticas).
            st.markdown("#### Cuentas dormidas con historial de cotización")
            dormant = _load_df(
                conn,
                """
                SELECT
                  s.entity_key AS email,
                  s.score,
                  s.created_at,
                  c.domain AS dominio,
                  c.organization_name_guess AS organizacion,
                  c.organization_type_guess AS tipo_org,
                  c.first_seen_at,
                  c.last_seen_at,
                  c.total_emails,
                  c.quote_email_count,
                  c.business_doc_email_count,
                  c.top_equipment_tags
                FROM opportunity_signals s
                JOIN contact_master c ON c.email = s.entity_key
                WHERE s.signal_type = 'dormant_contact'
                ORDER BY s.score DESC, s.created_at DESC
                LIMIT 30
                """,
            )
            if dormant.empty:
                st.info(
                    "Por ahora no se detectaron **cuentas dormidas** con historial de cotización significativo "
                    "según las señales heurísticas actuales."
                )
            else:
                dormant_display = dormant.copy()
                dormant_display["tipo_org"] = dormant_display["tipo_org"].apply(
                    lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                )
                dormant_display = dormant_display.rename(
                    columns={
                        "email": "Contacto (email)",
                        "dominio": "Dominio",
                        "organizacion": "Organización",
                        "tipo_org": "Tipo de organización",
                        "first_seen_at": "Primera actividad",
                        "last_seen_at": "Última actividad registrada",
                        "total_emails": "Total de correos",
                        "quote_email_count": "Correos con cotización",
                        "business_doc_email_count": "Correos con documentos comerciales",
                        "top_equipment_tags": "Equipos asociados (heurístico)",
                        "score": "Intensidad de la señal de cuenta dormida",
                        "created_at": "Señal detectada el",
                    }
                )
                st.dataframe(dormant_display, use_container_width=True, hide_index=True)
                st.caption(
                    "Estas cuentas combinan un historial relevante de cotización con ausencia de actividad reciente; "
                    "son candidatas para reactivación comercial."
                )

            st.divider()
            st.markdown("### Explorador por equipo")
            st.caption("Ahora está en una sección dedicada para una navegación más clara.")
            if st.button("Ir a Equipos", key="go_to_equipos"):
                _navigate_to("Equipos")

            return

        if page == "Equipos":
            _render_equipment_page(conn)
            return

        if page == "Contactos":
            st.subheader("Contactos")
            q = st.text_input("Buscar (email / dominio / organización)", value="")
            min_total = st.number_input("Mínimo de correos", min_value=0, value=3, step=1)
            st.caption("Busca por email, dominio u organización. Se priorizan coincidencias más exactas.")

            dfc = _load_df(
                conn,
                """
                SELECT
                  email, domain AS dominio, organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera, last_seen_at AS ultima,
                  total_emails AS total,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos
                FROM contact_master
                """,
            )
            dfc = dfc[dfc["total"] >= int(min_total)]
            qn = _normalize_query(q)
            if qn:
                score = _search_relevance_score(dfc, qn, ["email", "dominio", "organizacion"])
                dfc = dfc.assign(_search_score=score)
                dfc = dfc[dfc["_search_score"] > 0]
                dfc = dfc.sort_values(["_search_score", "total", "ultima"], ascending=[False, False, False])
            else:
                dfc = dfc.sort_values(["total", "ultima"], ascending=[False, False])
            st.caption(f"Resultados: {len(dfc):,}")
            # Nombres de columnas más amigables para la tabla principal.
            dfc_display = dfc.rename(
                columns={
                    "dominio": "Dominio",
                    "organizacion": "Organización",
                    "tipo_org": "Tipo de organización",
                    "primera": "Primera interacción",
                    "ultima": "Última interacción",
                    "total": "Total de correos",
                    "cotiz_email": "Correos con cotización",
                    "factura_email": "Correos con factura",
                    "compra_email": "Correos de compra/pedido",
                    "doc_emails": "Correos con documentos comerciales",
                    "equipos": "Equipos mencionados",
                }
            )
            st.dataframe(dfc_display.head(800), use_container_width=True, hide_index=True)

            st.divider()
            sel = st.selectbox("Seleccionar contacto", options=[""] + dfc["email"].head(400).tolist())
            if sel:
                row = _load_df(conn, "SELECT * FROM contact_master WHERE email=?", (sel,))
                if not row.empty:
                    r = row.iloc[0]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("**Identidad del contacto**")
                        st.markdown(f"- Email: `{r['email']}`")
                        st.markdown(f"- Dominio: `{r['domain']}`" if r.get("domain") else "- Dominio: (no detectado)")
                        org_name = r.get("organization_name_guess") or "Sin nombre de organización"
                        st.markdown(f"- Organización: {org_name}")
                        st.markdown(f"- Tipo de organización: {_friendly_org_type(r.get('organization_type_guess'))}")

                    with col2:
                        st.markdown("**Actividad en el tiempo**")
                        st.markdown(f"- Primera interacción: {r.get('first_seen_at') or 'N/D'}")
                        st.markdown(f"- Última interacción: {r.get('last_seen_at') or 'N/D'}")
                        total = r.get("total_emails") or 0
                        st.markdown(f"- Total de correos: {int(total):,}")
                        quotes = r.get("quote_email_count") or 0
                        invoices = r.get("invoice_email_count") or 0
                        purchases = r.get("purchase_email_count") or 0
                        st.markdown(
                            f"Se han detectado **{int(quotes)}** correos con términos de cotización, "
                            f"**{int(invoices)}** con términos de factura y "
                            f"**{int(purchases)}** relacionados con compra/pedido."
                        )

                    with col3:
                        st.markdown("**Documentos y equipos**")
                        doc_emails = r.get("business_doc_email_count") or r.get("business_doc_email_count".upper(), 0)
                        st.markdown(
                            f"- Correos con documentos comerciales: {int(doc_emails) if pd.notna(doc_emails) else 0}"
                        )
                        equipos = r.get("top_equipment_tags")
                        if equipos:
                            st.markdown("- Equipos más mencionados:")
                            st.markdown(equipos)
                        else:
                            st.markdown("- Equipos más mencionados: (no detectados)")

                    with st.expander("Ver datos técnicos del contacto"):
                        st.json(r.to_dict())

                    # Drill-down: documentos asociados al dominio del contacto.
                    st.markdown("### Documentos asociados a este contacto")
                    dom = r.get("domain")
                    if dom:
                        docs = _load_df(
                            conn,
                            """
                            SELECT
                              attachment_id,
                              sent_at,
                              doc_type,
                              filename,
                              sender_domain,
                              equipment_tags
                            FROM document_master
                            WHERE sender_domain = ?
                            ORDER BY sent_at DESC, attachment_id DESC
                            LIMIT 10
                            """,
                            (dom,),
                        )
                        if docs.empty:
                            st.info("No se encontraron documentos comerciales asociados a este contacto.")
                        else:
                            docs_display = docs.copy()
                            docs_display["doc_type"] = docs_display["doc_type"].apply(
                                lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
                            )
                            docs_display = docs_display.rename(
                                columns={
                                    "sent_at": "Fecha envío",
                                    "doc_type": "Tipo de documento",
                                    "filename": "Archivo",
                                    "sender_domain": "Dominio remitente",
                                    "equipment_tags": "Equipos mencionados",
                                }
                            )
                            st.dataframe(docs_display, use_container_width=True, hide_index=True)
                    else:
                        st.info("Este contacto no tiene dominio asociado para buscar documentos relacionados.")

                    # Drill-down: señales asociadas al contacto.
                    st.markdown("### Señales heurísticas asociadas a este contacto")
                    sig = _load_df(
                        conn,
                        """
                        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                        FROM opportunity_signals
                        WHERE entity_kind = 'contact' AND entity_key = ?
                        ORDER BY score DESC, created_at DESC
                        """,
                        (r["email"],),
                    )
                    if sig.empty:
                        st.info("No se detectaron señales específicas para este contacto.")
                    else:
                        sig["señal"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                        sig["explicación"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[1])
                        sig_display = sig[["señal", "explicación", "score", "created_at"]]
                        sig_display = sig_display.rename(
                            columns={
                                "score": "Intensidad de la señal",
                                "created_at": "Detectado el",
                            }
                        )
                        st.dataframe(sig_display, use_container_width=True, hide_index=True)
                        with st.expander("Ver detalles técnicos de las señales"):
                            st.dataframe(
                                sig[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]],
                                use_container_width=True,
                                hide_index=True,
                            )
            return

        if page == "Organizaciones":
            st.subheader("Organizaciones")
            q = st.text_input("Buscar (dominio / nombre)", value="", key="org_q_basic")
            min_total = st.number_input("Mínimo correos", min_value=0, value=8, step=1, key="org_min_basic")
            min_contacts = st.number_input(
                "Mínimo contactos", min_value=0, value=2, step=1, key="org_min_c_basic"
            )
            st.caption("Busca por dominio o nombre. Se priorizan coincidencias más exactas.")
            solo_unis_default = _consume_nav_flag("org_only_unis", False)
            solo_unis = st.checkbox(
                "Solo universidades con actividad de cotización",
                value=solo_unis_default,
            )

            dfo = _load_df(
                conn,
                """
                SELECT
                  domain AS dominio,
                  organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera,
                  last_seen_at AS ultima,
                  total_emails AS total,
                  total_contacts AS contactos,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos,
                  key_contacts AS contactos_clave
                FROM organization_master
                """,
            )
            dfo = dfo[dfo["total"] >= int(min_total)]
            dfo = dfo[dfo["contactos"] >= int(min_contacts)]
            if solo_unis:
                dfo = dfo[
                    (dfo["tipo_org"] == "education")
                    & ((dfo["cotiz_email"] > 0) | (dfo["doc_emails"] > 0))
                ]
            # Filtro adicional desde quick-actions: solo organizaciones con facturas.
            if _consume_nav_flag("org_only_invoices", False):
                dfo = dfo[(dfo["factura_email"] > 0)]
            # Filtro adicional: universidades con facturación.
            if _consume_nav_flag("org_only_unis_invoices", False):
                dfo = dfo[
                    (dfo["tipo_org"] == "education")
                    & (dfo["factura_email"] > 0)
                ]

            qn = _normalize_query(q)
            if qn:
                score = _search_relevance_score(dfo, qn, ["dominio", "organizacion"])
                dfo = dfo.assign(_search_score=score)
                dfo = dfo[dfo["_search_score"] > 0]
                dfo = dfo.sort_values(["_search_score", "total", "ultima"], ascending=[False, False, False])
            else:
                dfo = dfo.sort_values(["total", "ultima"], ascending=[False, False])
            st.caption(f"Resultados: {len(dfo):,}")

            # Nombres de columnas más amigables para la tabla principal.
            dfo_display = dfo.rename(
                columns={
                    "dominio": "Dominio",
                    "organizacion": "Organización",
                    "tipo_org": "Tipo de organización",
                    "primera": "Primera interacción",
                    "ultima": "Última interacción",
                    "total": "Total de correos",
                    "contactos": "Total de contactos",
                    "cotiz_email": "Correos con cotización",
                    "factura_email": "Correos con factura",
                    "compra_email": "Correos de compra/pedido",
                    "doc_emails": "Correos con documentos comerciales",
                    "equipos": "Equipos mencionados",
                    "contactos_clave": "Contactos clave (texto heurístico)",
                }
            )
            st.dataframe(dfo_display.head(800), use_container_width=True, hide_index=True)

            # Vista resumida de proveedores detectados (heurística basada en facturas y documentos comerciales).
            st.divider()
            st.markdown("### Proveedores detectados")
            st.caption(
                "Organizaciones tratadas como **proveedores** en base a facturas, órdenes de compra, "
                "documentos comerciales y listas de precios detectadas en el archivo histórico."
            )

            proveedores = _load_df(
                conn,
                """
                SELECT
                  domain AS dominio,
                  organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera,
                  last_seen_at AS ultima,
                  total_emails AS total,
                  total_contacts AS contactos,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  invoice_doc_count AS factura_docs,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos,
                  key_contacts AS contactos_clave
                FROM organization_master
                """,
            )
            proveedor_docs = _load_df(
                conn,
                """
                SELECT sender_domain, doc_type
                FROM document_master
                WHERE doc_type IN ('price_list', 'datasheet', 'purchase_order')
                """,
            )
            dominios_lista = set(
                proveedor_docs[proveedor_docs["doc_type"] == "price_list"]["sender_domain"].dropna().tolist()
            )
            dominios_ficha = set(
                proveedor_docs[proveedor_docs["doc_type"] == "datasheet"]["sender_domain"].dropna().tolist()
            )
            dominios_compra = set(
                proveedor_docs[proveedor_docs["doc_type"] == "purchase_order"]["sender_domain"].dropna().tolist()
            )

            if not proveedores.empty:
                proveedores["es_proveedor"] = (
                    (proveedores["factura_email"] > 0)
                    | (proveedores["factura_docs"] > 0)
                    | (proveedores["compra_email"] > 0)
                    | (proveedores["doc_emails"] > 0)
                    | proveedores["dominio"].isin(dominios_lista)
                    | proveedores["dominio"].isin(dominios_ficha)
                    | proveedores["dominio"].isin(dominios_compra)
                )
                proveedores = proveedores[proveedores["es_proveedor"]]

            if proveedores.empty:
                st.info(
                    "Aún no se detectan organizaciones con suficiente evidencia documental para clasificarlas como "
                    "proveedores. Cuando el mart tenga facturas u órdenes de compra, aparecerán aquí."
                )
            else:
                proveedores["tiene_lista_precios"] = proveedores["dominio"].isin(dominios_lista)
                proveedores["tiene_ficha_tecnica"] = proveedores["dominio"].isin(dominios_ficha)
                proveedores["tiene_documentos_compra"] = proveedores["dominio"].isin(dominios_compra)

                def _evidencia_proveedor(row: pd.Series) -> str:
                    partes: list[str] = []
                    if (row.get("factura_email") or 0) > 0 or (row.get("factura_docs") or 0) > 0:
                        partes.append("facturas detectadas")
                    if (row.get("compra_email") or 0) > 0 or row.get("tiene_documentos_compra"):
                        partes.append("órdenes de compra / correos de compra")
                    if (row.get("doc_emails") or 0) > 0:
                        partes.append("correos con documentos comerciales")
                    if row.get("tiene_lista_precios"):
                        partes.append("listas de precios")
                    if row.get("tiene_ficha_tecnica"):
                        partes.append("fichas técnicas")
                    return ", ".join(partes) if partes else "Evidencia comercial limitada"

                proveedores["evidencia"] = proveedores.apply(_evidencia_proveedor, axis=1)
                proveedores["tipo_org"] = proveedores["tipo_org"].apply(
                    lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                )

                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    f_facturas = st.checkbox("Solo con facturas", value=False)
                with fc2:
                    f_listas = st.checkbox("Solo con listas de precios / fichas técnicas", value=False)
                with fc3:
                    f_compra = st.checkbox("Solo con órdenes de compra / compra", value=False)

                proveedores_filtrado = proveedores.copy()
                if f_facturas:
                    proveedores_filtrado = proveedores_filtrado[
                        (proveedores_filtrado["factura_email"] > 0) | (proveedores_filtrado["factura_docs"] > 0)
                    ]
                if f_listas:
                    proveedores_filtrado = proveedores_filtrado[
                        proveedores_filtrado["tiene_lista_precios"] | proveedores_filtrado["tiene_ficha_tecnica"]
                    ]
                if f_compra:
                    proveedores_filtrado = proveedores_filtrado[
                        (proveedores_filtrado["compra_email"] > 0) | proveedores_filtrado["tiene_documentos_compra"]
                    ]

                proveedores_filtrado = proveedores_filtrado.sort_values(
                    ["factura_docs", "factura_email", "doc_emails", "total"],
                    ascending=[False, False, False, False],
                )

                proveedores_display = proveedores_filtrado.rename(
                    columns={
                        "dominio": "Dominio",
                        "organizacion": "Organización",
                        "tipo_org": "Tipo de organización",
                        "primera": "Primera actividad",
                        "ultima": "Última actividad",
                        "total": "Total de correos",
                        "contactos": "Total de contactos",
                        "cotiz_email": "Correos con cotización",
                        "factura_email": "Correos con factura",
                        "factura_docs": "Documentos tipo factura",
                        "compra_email": "Correos de compra/pedido",
                        "doc_emails": "Correos con documentos comerciales",
                        "equipos": "Equipos asociados (heurístico)",
                        "contactos_clave": "Contactos clave (texto heurístico)",
                        "evidencia": "Evidencia de proveedor",
                    }
                )
                st.dataframe(proveedores_display.head(200), use_container_width=True, hide_index=True)

            st.divider()
            sel = st.selectbox("Seleccionar dominio", options=[""] + dfo["dominio"].head(400).tolist())
            if sel:
                row = _load_df(conn, "SELECT * FROM organization_master WHERE domain=?", (sel,))
                if not row.empty:
                    r = row.iloc[0]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("**Identidad de la organización**")
                        st.markdown(f"- Dominio: `{r['domain']}`")
                        org_name = r.get("organization_name_guess") or "Sin nombre de organización"
                        st.markdown(f"- Organización: {org_name}")
                        st.markdown(f"- Tipo de organización: {_friendly_org_type(r.get('organization_type_guess'))}")

                    with col2:
                        st.markdown("**Actividad en el tiempo**")
                        st.markdown(f"- Primera interacción: {r.get('first_seen_at') or 'N/D'}")
                        st.markdown(f"- Última interacción: {r.get('last_seen_at') or 'N/D'}")
                        total = r.get("total_emails") or 0
                        contactos = r.get("total_contacts") or 0
                        st.markdown(f"- Total de correos: {int(total):,}")
                        st.markdown(f"- Total de contactos detectados: {int(contactos):,}")

                        quotes = r.get("quote_email_count") or 0
                        invoices = r.get("invoice_email_count") or 0
                        purchases = r.get("purchase_email_count") or 0
                        st.markdown(
                            f"Correos detectados: **{int(quotes)}** con cotización, "
                            f"**{int(invoices)}** con factura y "
                            f"**{int(purchases)}** de compra/pedido."
                        )

                    with col3:
                        st.markdown("**Documentos y equipos**")
                        doc_emails = r.get("business_doc_email_count") or 0
                        st.markdown(f"- Correos con documentos comerciales: {int(doc_emails)}")
                        equipos = r.get("top_equipment_tags")
                        if equipos:
                            st.markdown("- Equipos más mencionados:")
                            st.markdown(equipos)
                        else:
                            st.markdown("- Equipos más mencionados: (no detectados)")
                        key_contacts = r.get("key_contacts")
                        if key_contacts:
                            st.markdown("**Contactos clave (texto heurístico)**")
                            st.markdown(key_contacts)

                    with st.expander("Ver datos técnicos de la organización"):
                        st.json(r.to_dict())

                    # Drill-down: contactos clave de esta organización.
                    st.markdown("### Contactos de esta organización")
                    contacts = _load_df(
                        conn,
                        """
                        SELECT
                          email,
                          domain AS dominio,
                          organization_name_guess AS organizacion,
                          first_seen_at AS primera,
                          last_seen_at AS ultima,
                          total_emails AS total,
                          quote_email_count AS cotiz_email,
                          invoice_email_count AS factura_email,
                          purchase_email_count AS compra_email,
                          business_doc_email_count AS doc_emails
                        FROM contact_master
                        WHERE domain = ?
                        ORDER BY total_emails DESC, last_seen_at DESC
                        LIMIT 10
                        """,
                        (r["domain"],),
                    )
                    if contacts.empty:
                        st.info("No se encontraron contactos asociados a esta organización.")
                    else:
                        contacts_display = contacts.rename(
                            columns={
                                "dominio": "Dominio",
                                "organizacion": "Organización",
                                "primera": "Primera interacción",
                                "ultima": "Última interacción",
                                "total": "Total de correos",
                                "cotiz_email": "Correos con cotización",
                                "factura_email": "Correos con factura",
                                "compra_email": "Correos de compra/pedido",
                                "doc_emails": "Correos con documentos comerciales",
                            }
                        )
                        st.dataframe(contacts_display, use_container_width=True, hide_index=True)

                    # Drill-down: documentos recientes de la organización.
                    st.markdown("### Documentos comerciales recientes")
                    docs = _load_df(
                        conn,
                        """
                        SELECT
                          attachment_id,
                          sent_at,
                          doc_type,
                          filename,
                          sender_domain,
                          equipment_tags
                        FROM document_master
                        WHERE sender_domain = ?
                        ORDER BY sent_at DESC, attachment_id DESC
                        LIMIT 10
                        """,
                        (r["domain"],),
                    )
                    if docs.empty:
                        st.info("No se encontraron documentos comerciales recientes para esta organización.")
                    else:
                        docs_display = docs.copy()
                        docs_display["doc_type"] = docs_display["doc_type"].apply(
                            lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
                        )
                        docs_display = docs_display.rename(
                            columns={
                                "sent_at": "Fecha envío",
                                "doc_type": "Tipo de documento",
                                "filename": "Archivo",
                                "sender_domain": "Dominio remitente",
                                "equipment_tags": "Equipos mencionados",
                            }
                        )
                        st.dataframe(docs_display, use_container_width=True, hide_index=True)

                    # Drill-down: señales relacionadas con la organización.
                    st.markdown("### Señales heurísticas relacionadas con esta organización")
                    sig = _load_df(
                        conn,
                        """
                        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                        FROM opportunity_signals
                        WHERE entity_kind = 'organization' AND entity_key = ?
                        ORDER BY score DESC, created_at DESC
                        """,
                        (r["domain"],),
                    )
                    if sig.empty:
                        st.info("No se detectaron señales específicas para esta organización.")
                    else:
                        sig["señal"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                        sig["explicación"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[1])
                        sig_display = sig[["señal", "explicación", "score", "created_at"]]
                        sig_display = sig_display.rename(
                            columns={
                                "score": "Intensidad de la señal",
                                "created_at": "Detectado el",
                            }
                        )
                        st.dataframe(sig_display, use_container_width=True, hide_index=True)
                        with st.expander("Ver detalles técnicos de las señales"):
                            st.dataframe(
                                sig[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]],
                                use_container_width=True,
                                hide_index=True,
                            )
            return

        if page == "Documentos":
            st.subheader("Documentos")
            q = st.text_input("Buscar (archivo o contenido)", value="", key="doc_q_basic")
            dfd = _load_df(
                conn,
                """
                SELECT
                  attachment_id, sent_at, doc_type, filename, sender_domain,
                  extracted_preview_clean, preview_quality_score, equipment_tags
                FROM document_master
                """,
            )
            # Quick-action: solo documentos de cotización.
            if st.session_state.get("docs_only_quotes"):
                dfd = dfd[dfd["doc_type"] == "quote"]

            if q.strip():
                ql = q.strip().lower()
                mask = (
                    dfd["filename"].fillna("").str.lower().str.contains(ql)
                    | dfd["extracted_preview_clean"].fillna("").str.lower().str.contains(ql)
                )
                dfd = dfd[mask]
            dfd = dfd.sort_values(["sent_at", "attachment_id"], ascending=[False, False])
            dfd_display = dfd.copy()
            dfd_display["doc_type"] = dfd_display["doc_type"].apply(
                lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
            )
            dfd_display = dfd_display.rename(
                columns={
                    "sent_at": "Fecha envío",
                    "doc_type": "Tipo de documento",
                    "filename": "Archivo",
                    "sender_domain": "Dominio remitente",
                    "extracted_preview_clean": "Texto relevante encontrado",
                    "preview_quality_score": "Calidad de la extracción",
                    "equipment_tags": "Equipos mencionados",
                }
            )
            st.dataframe(dfd_display.head(400), use_container_width=True, hide_index=True)

            # Detalle resumido de un documento seleccionado.
            st.divider()
            if not dfd.empty:
                options = dfd.head(200).apply(
                    lambda r: f"{r['attachment_id']} — {str(r['sent_at'])[:10]} — {r['filename']}",
                    axis=1,
                ).tolist()
                selected_label = st.selectbox(
                    "Ver detalle de un documento",
                    options=[""] + options,
                )
                if selected_label:
                    sel_id = int(selected_label.split(" — ")[0])
                    drow_df = _load_df(
                        conn,
                        """
                        SELECT
                          attachment_id,
                          sent_at,
                          doc_type,
                          filename,
                          sender_domain,
                          extracted_preview_clean,
                          preview_quality_score,
                          equipment_tags
                        FROM document_master
                        WHERE attachment_id = ?
                        """,
                        (sel_id,),
                    )
                    if not drow_df.empty:
                        d = drow_df.iloc[0]
                        st.markdown("### Resumen del documento seleccionado")
                        st.markdown(
                            f"Detectado como **{_friendly_doc_type(d.get('doc_type'))}** "
                            "según el contenido del adjunto."
                        )
                        st.markdown(f"- Fecha de envío: {d.get('sent_at')}")
                        st.markdown(f"- Archivo: `{d.get('filename')}`")
                        st.markdown(f"- Dominio remitente: `{d.get('sender_domain')}`")
                        score = d.get("preview_quality_score")
                        if pd.notna(score):
                            st.markdown(f"- Calidad de la extracción de texto: {score:.2f}")
                        equipos = d.get("equipment_tags")
                        if equipos:
                            st.markdown(f"- Equipos mencionados: {equipos}")
                        else:
                            st.markdown("- Equipos mencionados: (no detectados)")

                        with st.expander("Ver texto extraído (resumen)"):
                            preview = d.get("extracted_preview_clean") or "(sin texto extraído disponible)"
                            st.write(preview)

                        with st.expander("Ver datos técnicos del documento"):
                            st.json(d.to_dict())
            return

        if page == "Oportunidades":
            st.subheader("Oportunidades")
            dfs = _load_df(
                conn,
                """
                SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                FROM opportunity_signals
                ORDER BY score DESC, created_at DESC
                """,
            )
            dfs["señal"] = dfs["signal_type"].apply(lambda x: _signal_label(str(x))[0])
            dfs["explicación"] = dfs["signal_type"].apply(lambda x: _signal_label(str(x))[1])

            # Filtros amigables por tipo de señal, entidad y score mínimo.
            signal_options = ["Todas", "Cotización + documento", "Universidad con cotización", "Cuenta dormida", "Tema de equipo recurrente"]
            # Si venimos desde quick-action de cuentas dormidas, seleccionar por defecto esa opción.
            default_signal = 0
            if st.session_state.pop("opp_signal_filter", None) == "dormant_contact":
                default_signal = signal_options.index("Cuenta dormida")
            tipo_señal = st.selectbox("Tipo de señal", options=signal_options, index=default_signal)
            signal_map = {
                "Cotización + documento": "quote_email_plus_quote_doc",
                "Universidad con cotización": "education_with_quote_activity",
                "Cuenta dormida": "dormant_contact",
                "Tema de equipo recurrente": "repeated_equipment_theme",
            }
            if tipo_señal != "Todas":
                dfs = dfs[dfs["signal_type"] == signal_map[tipo_señal]]

            entity_options = ["Todas", "Contacto", "Organización"]
            tipo_entidad = st.selectbox("Entidad asociada", options=entity_options)
            if tipo_entidad == "Contacto":
                dfs = dfs[dfs["entity_kind"] == "contact"]
            elif tipo_entidad == "Organización":
                dfs = dfs[dfs["entity_kind"] == "organization"]

            min_score = st.number_input("Score mínimo de la señal", min_value=0.0, max_value=1000.0, value=0.0, step=1.0)
            dfs = dfs[dfs["score"] >= float(min_score)]

            # Panel rápido: señales por tipo + intensidad máxima para priorización.
            if not dfs.empty:
                summary = (
                    dfs.groupby("signal_type", dropna=False)
                    .agg(total=("signal_type", "count"), score_max=("score", "max"))
                    .reset_index()
                )
                summary["señal"] = summary["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                summary = summary.sort_values(["total", "score_max"], ascending=[False, False]).head(6)
                st.markdown("#### Prioridad rápida")
                st.dataframe(
                    summary[["señal", "total", "score_max"]].rename(
                        columns={"total": "Cantidad", "score_max": "Score máximo"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            # Traducir entity_kind a etiquetas legibles.
            dfs_display = dfs.copy()
            dfs_display["Entidad"] = dfs_display["entity_kind"].map(
                {"contact": "Contacto", "organization": "Organización"}
            ).fillna(dfs_display["entity_kind"])

            main_cols = ["señal", "explicación", "Entidad", "entity_key", "score", "created_at"]
            dfs_display = dfs_display[main_cols].rename(
                columns={
                    "entity_key": "Clave (email/dominio)",
                    "score": "Intensidad de la señal",
                    "created_at": "Detectado el",
                }
            )

            st.caption(f"Resultados: {len(dfs_display):,}")
            st.dataframe(
                dfs_display.head(600),
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("Ver detalles técnicos de las señales"):
                st.dataframe(
                    dfs[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]].head(600),
                    use_container_width=True,
                    hide_index=True,
                )
            return
    finally:
        conn.close()


if __name__ == "__main__":
    main()

