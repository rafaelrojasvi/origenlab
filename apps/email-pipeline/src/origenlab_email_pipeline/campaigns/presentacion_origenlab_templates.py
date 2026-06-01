"""Spanish templates — Presentación OrigenLab + mención Cyber suave (read-only)."""

from __future__ import annotations

OPT_OUT_LINE_ES = (
    "Si prefiere no recibir información comercial de OrigenLab, puede responder 'remover'."
)

CYBER_SOFT_LINE = (
    "Hasta el 7 de junio, en equipos seleccionados puede aplicar una mejora comercial "
    "referencial de 5–10%, siempre sujeta a marca, disponibilidad y confirmación "
    "técnica/comercial."
)

PRESENTACION_BATCH1_SUBJECT = "Presentación OrigenLab | equipos para laboratorio"


def _greeting(contact_name: str) -> str:
    name = (contact_name or "").strip()
    return f"Estimado/a {name}," if name else "Estimado/a,"


def template_presentacion_batch1_es(*, contact_name: str = "") -> tuple[str, str]:
    """Presentación empresa — batch 1 (texto operador aprobado)."""
    body = f"""{_greeting(contact_name)}

Junto con saludar, quería presentar brevemente OrigenLab, empresa chilena enfocada en equipos e insumos para laboratorio.

Apoyamos a laboratorios de investigación, control de calidad, alimentos, agua, salud e industria con líneas como centrífugas, microcentrífugas, balanzas, incubadoras, homogeneizadores, sonicadores, reactores de laboratorio y equipos de preparación de muestras.

Trabajamos con cotización según requerimiento técnico, ayudando a revisar capacidad, aplicación, marca, disponibilidad y alternativas según el uso del laboratorio.

Además, hasta el 7 de junio podemos revisar una mejora comercial Cyber de 5% a 10% en equipos seleccionados, sujeto a marca, disponibilidad y confirmación técnica/comercial.

Si están evaluando compra, reposición o cotización referencial durante este semestre, puede responder este correo indicando el equipo o familia de interés y revisamos una propuesta acotada.

Saludos cordiales,"""
    return PRESENTACION_BATCH1_SUBJECT, body


def template_followup_old_es(
    *,
    contact_name: str = "",
    organization: str = "",
    topic_hint: str = "",
) -> tuple[str, str]:
    """Follow-up comercial antiguo — retomar hilo previo."""
    org = (organization or "su laboratorio").strip()
    topic = topic_hint.strip()
    topic_line = (
        f" sobre {topic}" if topic else " el contacto previo sobre equipamiento de laboratorio"
    )
    subject = f"Retomar consulta — OrigenLab | {org}"[:78]
    body = f"""{_greeting(contact_name)}

Junto con saludar, quería retomar brevemente{topic_line}.

Seguimos disponibles para apoyar con cotización técnica, alternativas de marca y disponibilidad según su aplicación.

{CYBER_SOFT_LINE}

Si el requerimiento sigue vigente, puede responder indicando equipo o familia de interés y revisamos una propuesta acotada.

Saludos cordiales,"""
    return subject, body


def template_hold_personalized_es(
    *,
    contact_name: str = "",
    case_label: str,
    personalized_action: str,
    history_note: str = "",
) -> tuple[str, str]:
    """Mensaje personalizado para caso activo (no campaña genérica)."""
    subject = f"OrigenLab — {case_label}"[:78]
    hist = f"\n\nContexto: {history_note.strip()}" if history_note.strip() else ""
    body = f"""{_greeting(contact_name)}

{personalized_action}{hist}

Saludos cordiales,"""
    return subject, body


def template_presentacion_send_now_es(
    *,
    contact_name: str,
    organization: str,
    product_angle: str,
    history_note: str = "",
) -> tuple[str, str]:
    """Legacy wrapper — usa plantilla batch 1."""
    _ = organization, product_angle, history_note
    return template_presentacion_batch1_es(contact_name=contact_name)


def template_same_domain_review_note(
    *,
    organization: str,
    domain: str,
    history_note: str,
) -> str:
    return (
        f"Revisar historial del dominio {domain} ({organization}) antes de cualquier envío. "
        f"{history_note}. No incluir en envío automático."
    )


def render_batch_messages_markdown(
    rows: list,
    *,
    title: str,
    intro: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        intro,
        "",
        "**No enviar desde este archivo.** Revisión humana obligatoria.",
        "",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## {idx}. {row.email}",
                "",
                f"- **Organización:** {row.organization}",
                f"- **Clasificación:** {row.classification}",
                f"- **Prioridad:** {row.priority_score:.1f}",
                f"- **Razón:** {row.reason_for_inclusion}",
                "",
                f"**Asunto:** {row.suggested_subject}",
                "",
                "```",
                row.suggested_message,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_messages_markdown(rows: list) -> str:
    """Build operator message preview markdown from legacy send-now rows."""
    lines = [
        "# Presentación OrigenLab — borradores (solo revisión, sin envío)",
        "",
        "Tema: presentación de OrigenLab como proveedor chileno de equipamiento de laboratorio.",
        "Mención Cyber suave: mejora comercial referencial 5–10% hasta el 7 de junio, sujeta a confirmación.",
        "",
        "**No enviar desde este archivo.** Revisión humana obligatoria.",
        "",
    ]
    for idx, row in enumerate(rows, start=1):
        bucket = getattr(row, "bucket", "")
        lines.extend(
            [
                f"## {idx}. {row.email}",
                "",
                f"- **Organización:** {row.organization}",
                f"- **Bucket:** {bucket}",
                f"- **Prioridad:** {row.priority_score:.1f}",
                f"- **Razón:** {row.reason_for_inclusion}",
                "",
                f"**Asunto:** {row.suggested_subject}",
                "",
                "```",
                row.suggested_message,
                "```",
                "",
            ]
        )
    return "\n".join(lines)
