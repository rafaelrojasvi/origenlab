from __future__ import annotations

from typing import Any

MARKETING_VARIANT_GENERAL = "presentacion_general"
MARKETING_VARIANT_UNIVERSIDADES = "universidades_investigacion"
MARKETING_VARIANT_HOSPITALES = "hospitales_laboratorio_clinico"
MARKETING_VARIANT_INDUSTRIA = "industria_qa_alimentos"
MARKETING_VARIANT_PUBLICO = "instituciones_publicas_compras"
MARKETING_VARIANT_FOLLOWUP = "followup_sin_respuesta"

MARKETING_VARIANT_TYPES: tuple[str, ...] = (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_UNIVERSIDADES,
    MARKETING_VARIANT_HOSPITALES,
    MARKETING_VARIANT_INDUSTRIA,
    MARKETING_VARIANT_PUBLICO,
    MARKETING_VARIANT_FOLLOWUP,
)

CANONICAL_BASE_PRESENTATION_EMAIL_ES = """Estimados/as,

Junto con saludar, quisiera presentarles OrigenLab, empresa enfocada en equipos e insumos para laboratorio, con atencion cercana y soporte comercial para apoyar requerimientos tecnicos y cotizaciones.

Entre nuestras soluciones destacamos osmometro crioscopico Knauer, reactivos y equipamiento para electroforesis Serva, y dispersores Ultra Turrax IKA, entre otras lineas para distintas necesidades de laboratorio.

Si le interesa, con gusto podemos compartir informacion de productos, alternativas segun su aplicacion o preparar una cotizacion.

Puede escribirnos a contacto@origenlab.cl o al WhatsApp +56 9 6256 7816.
"""

CANONICAL_OUTREACH_SENDER_NAME = "Tatiana Vivanco"
CANONICAL_OUTREACH_SIGNATURE_BLOCK = """Saludos cordiales,

Tatiana Vivanco
OrigenLab | Equipos para laboratorio
Valdivia, Chile
contacto@origenlab.cl | +56 9 6256 7816
www.origenlab.cl"""

MARKETING_VARIANT_BRIEFS: dict[str, str] = {
    MARKETING_VARIANT_GENERAL: (
        "Correo de presentacion comercial inicial, transversal, sin asumir demasiados detalles del receptor."
    ),
    MARKETING_VARIANT_UNIVERSIDADES: (
        "Enfoque academico / investigacion: laboratorios universitarios, docencia, investigacion aplicada."
    ),
    MARKETING_VARIANT_HOSPITALES: (
        "Enfoque salud / laboratorio clinico: tono sobrio, compras y requerimientos operativos."
    ),
    MARKETING_VARIANT_INDUSTRIA: (
        "Enfoque industria / QA / alimentos: control de calidad, analisis, continuidad operativa."
    ),
    MARKETING_VARIANT_PUBLICO: (
        "Enfoque instituciones publicas / compras: tono formal, claro y util para cotizacion o ficha."
    ),
    MARKETING_VARIANT_FOLLOWUP: (
        "Seguimiento breve a presentacion ya enviada, sin presionar demasiado y con CTA claro."
    ),
}

MARKETING_VARIANT_PRODUCT_HINTS: dict[str, str] = {
    MARKETING_VARIANT_GENERAL: "Usar ejemplos de productos solo si ayudan a ilustrar el tipo de soluciones.",
    MARKETING_VARIANT_UNIVERSIDADES: (
        "Si aplica, mencionar lineas ligadas a investigacion, docencia o electroforesis de forma concreta."
    ),
    MARKETING_VARIANT_HOSPITALES: (
        "Si aplica, priorizar lenguaje de laboratorio clinico, soporte comercial y requerimientos especificos."
    ),
    MARKETING_VARIANT_INDUSTRIA: (
        "Si aplica, conectar la linea de producto con control de calidad, analisis o procesos de laboratorio."
    ),
    MARKETING_VARIANT_PUBLICO: (
        "Si aplica, mantener ejemplos breves y utiles para instituciones que piden informacion o cotizacion."
    ),
    MARKETING_VARIANT_FOLLOWUP: (
        "No recargar con muchos productos; recordatorio breve y un solo foco comercial si existe."
    ),
}


def is_marketing_outreach_case(meta: dict[str, Any] | None, expected_label: str | None = None) -> bool:
    m = meta or {}
    if bool(m.get("marketing_outreach")):
        return True
    label = (expected_label or m.get("case_type") or "").strip().lower()
    return label in {"marketing_outreach", "outreach", "marketing_presentation"}


def marketing_outreach_supplement(meta: dict[str, Any] | None) -> dict[str, str]:
    m = meta or {}
    variant = str(m.get("variant_type") or MARKETING_VARIANT_GENERAL).strip()
    if variant not in MARKETING_VARIANT_TYPES:
        variant = MARKETING_VARIANT_GENERAL
    out = {
        "purpose": "primer contacto comercial / presentacion de OrigenLab",
        "variant_type": variant,
        "variant_brief": MARKETING_VARIANT_BRIEFS[variant],
        "variant_product_hint": MARKETING_VARIANT_PRODUCT_HINTS[variant],
        "canonical_base_email_es": CANONICAL_BASE_PRESENTATION_EMAIL_ES,
        "canonical_sender_name": CANONICAL_OUTREACH_SENDER_NAME,
        "canonical_signature_block": CANONICAL_OUTREACH_SIGNATURE_BLOCK,
        "recipient_name": str(m.get("recipient_name") or "").strip(),
        "institution_name": str(m.get("institution_name") or "").strip(),
        "sector": str(m.get("sector") or "").strip(),
        "product_focus": str(m.get("product_focus") or "").strip(),
        "use_case": str(m.get("use_case") or "").strip(),
        "custom_note": str(m.get("custom_note") or "").strip(),
        "contact_email_record": str(m.get("contact_email") or "").strip(),
    }
    return {k: v for k, v in out.items() if v}


def build_marketing_outreach_seed_body(
    *,
    variant_type: str,
    recipient_name: str | None,
    institution_name: str | None,
    sector: str | None,
    product_focus: str | None,
    use_case: str | None,
    custom_note: str | None,
) -> str:
    variant = variant_type if variant_type in MARKETING_VARIANT_TYPES else MARKETING_VARIANT_GENERAL
    lines = [
        "Objetivo: redactar un correo de presentacion comercial inicial de OrigenLab en espanol de Chile.",
        "No es soporte ni respuesta transaccional: es outreach de presentacion con revision humana posterior.",
        f"Variante solicitada: {variant}.",
        f"Descripcion de variante: {MARKETING_VARIANT_BRIEFS[variant]}",
        "",
        "Base canonica sugerida para reescribir y mejorar:",
        CANONICAL_BASE_PRESENTATION_EMAIL_ES.strip(),
    ]
    if recipient_name:
        lines.append(f"Nombre de destinatario confirmado: {recipient_name.strip()}.")
    if institution_name:
        lines.append(f"Institucion confirmada: {institution_name.strip()}.")
    if sector:
        lines.append(f"Sector confirmado: {sector.strip()}.")
    if product_focus:
        lines.append(f"Foco de producto confirmado: {product_focus.strip()}.")
    if use_case:
        lines.append(f"Caso de uso confirmado: {use_case.strip()}.")
    if custom_note:
        lines.append(f"Nota adicional confirmada: {custom_note.strip()}.")
    lines.extend(
        [
            "",
            "Pedir al modelo:",
            "- mejorar redaccion, propuesta de valor y CTA",
            "- mantener tono comercial sobrio y creible",
            "- no inventar hechos del destinatario",
            "- personalizar solo con los datos confirmados arriba",
            "- usar a Tatiana Vivanco como remitente canonico",
            "- no dejar placeholders como [Tu Nombre] o [Institucion]",
            "- cerrar con firma aprobada de Tatiana / OrigenLab",
        ]
    )
    return "\n".join(lines).strip()
