from __future__ import annotations

from dataclasses import dataclass

from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB
from .marketing_outreach import (
    MARKETING_VARIANT_FOLLOWUP,
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_HOSPITALES,
    MARKETING_VARIANT_INDUSTRIA,
    MARKETING_VARIANT_PUBLICO,
    MARKETING_VARIANT_UNIVERSIDADES,
)


@dataclass(frozen=True)
class DraftResult:
    text: str
    provider_name: str
    abstained: bool
    notes: str


class DraftGenerator:
    def generate(self, prompt_blocks: dict[str, object]) -> DraftResult:  # pragma: no cover - interface
        raise NotImplementedError


class MockDraftGenerator(DraftGenerator):
    """
    Safe default: works offline/no API key.
    Produces a conservative draft or abstains when context is too thin.
    """

    @staticmethod
    def _clean(v: object) -> str:
        return str(v or "").strip()

    def _mock_outreach_subject(self, *, subject: str, variant: str, institution_name: str) -> str:
        if variant == MARKETING_VARIANT_FOLLOWUP:
            if subject:
                return f"Asunto: Seguimiento | {subject}"
            if institution_name:
                return f"Asunto: Seguimiento presentacion OrigenLab | {institution_name}"
            return "Asunto: Seguimiento presentacion OrigenLab"
        if subject:
            return f"Asunto: {subject}"
        if institution_name:
            return f"Asunto: Presentacion OrigenLab | {institution_name}"
        return "Asunto: Presentacion OrigenLab"

    def _mock_outreach_greeting(self, *, recipient_name: str, institution_name: str) -> str:
        if recipient_name:
            return f"Estimada/o {recipient_name}:"
        if institution_name:
            return f"Estimados/as {institution_name}:"
        return "Estimados/as:"

    def _mock_outreach_intro(self, *, variant: str, institution_name: str) -> str:
        inst = institution_name or "su institucion"
        if variant == MARKETING_VARIANT_FOLLOWUP:
            return (
                f"Retomo este contacto para compartir una breve presentacion de OrigenLab y quedar disponibles "
                f"si en {inst} les interesa revisar alternativas para laboratorio."
            )
        return (
            "Junto con saludar, quisiera presentarles OrigenLab, empresa enfocada en equipos e insumos "
            "para laboratorio, con atencion cercana y soporte comercial para apoyar requerimientos "
            "tecnicos y cotizaciones."
        )

    def _mock_outreach_value(self, *, variant: str, use_case: str) -> str:
        uc = use_case or ""
        if variant == MARKETING_VARIANT_UNIVERSIDADES:
            return (
                "Podemos apoyar laboratorios de docencia e investigacion con alternativas de equipamiento "
                "e insumos segun aplicacion y necesidad tecnica."
            )
        if variant == MARKETING_VARIANT_HOSPITALES:
            return (
                "Trabajamos con un enfoque sobrio y practico para apoyar evaluacion de opciones, informacion "
                "de producto y procesos de cotizacion en laboratorio clinico."
            )
        if variant == MARKETING_VARIANT_INDUSTRIA:
            return (
                "Buscamos apoyar procesos de analisis y control de calidad con soluciones de laboratorio "
                "ajustadas al uso requerido."
            )
        if variant == MARKETING_VARIANT_PUBLICO:
            return (
                "Podemos compartir informacion comercial y tecnica de manera clara para apoyar solicitudes "
                "de informacion o procesos de cotizacion."
            )
        if variant == MARKETING_VARIANT_FOLLOWUP:
            return (
                f"Si hoy estan revisando {uc}, con gusto podemos compartir una referencia breve de productos "
                "o alternativas aplicables."
                if uc
                else "Si les parece oportuno, podemos compartir una referencia breve de productos o alternativas aplicables."
            )
        return (
            f"Nuestro objetivo es ayudar a encontrar alternativas utiles para {uc}."
            if uc
            else "Nuestro objetivo es ayudar a encontrar alternativas utiles segun el contexto de cada laboratorio."
        )

    def _mock_outreach_product_line(self, *, product_focus: str, variant: str, use_case: str) -> str:
        pf = product_focus or ""
        uc = use_case or ""
        if pf:
            if uc:
                return f"En particular, podemos compartir informacion sobre {pf} para {uc}."
            return f"En particular, podemos compartir informacion sobre {pf}."
        if variant == MARKETING_VARIANT_UNIVERSIDADES:
            return "Por ejemplo, podemos apoyar lineas ligadas a electroforesis, reactivos y equipamiento de laboratorio."
        if variant == MARKETING_VARIANT_HOSPITALES:
            return "Por ejemplo, podemos compartir alternativas de equipamiento para laboratorio clinico y sus aplicaciones."
        if variant == MARKETING_VARIANT_INDUSTRIA:
            return "Por ejemplo, podemos revisar soluciones orientadas a analisis, preparacion de muestras o control de calidad."
        if variant == MARKETING_VARIANT_PUBLICO:
            return "Si les resulta util, podemos enviar una referencia breve de familias de productos segun su necesidad."
        return "Si les resulta util, podemos compartir una referencia breve de lineas y aplicaciones."

    def _mock_outreach_cta(self, *, variant: str, institution_name: str, custom_note: str) -> str:
        inst = institution_name or "su equipo"
        if variant == MARKETING_VARIANT_FOLLOWUP:
            return (
                f"Si en {inst} les interesa, puedo enviar una seleccion breve de alternativas o coordinar una "
                "conversacion inicial para entender mejor el requerimiento."
            )
        if custom_note:
            return (
                f"Si les interesa, con gusto podemos compartir informacion de productos, alternativas segun aplicacion "
                f"o preparar una cotizacion. Nota considerada para revision: {custom_note}"
            )
        return (
            "Si les interesa, con gusto podemos compartir informacion de productos, alternativas segun aplicacion "
            "o preparar una cotizacion."
        )

    def _build_mock_outreach(self, *, prompt_blocks: dict[str, object], subject: str, ol_sig: str) -> DraftResult:
        supp = dict(prompt_blocks.get("marketing_outreach_supplement") or {})
        variant = self._clean(supp.get("variant_type")) or MARKETING_VARIANT_GENERAL
        recipient_name = self._clean(supp.get("recipient_name"))
        institution_name = self._clean(supp.get("institution_name"))
        product_focus = self._clean(supp.get("product_focus"))
        use_case = self._clean(supp.get("use_case"))
        custom_note = self._clean(supp.get("custom_note"))
        draft = (
            f"{self._mock_outreach_subject(subject=subject, variant=variant, institution_name=institution_name)}\n\n"
            f"{self._mock_outreach_greeting(recipient_name=recipient_name, institution_name=institution_name)}\n\n"
            f"{self._mock_outreach_intro(variant=variant, institution_name=institution_name)}\n\n"
            f"{self._mock_outreach_value(variant=variant, use_case=use_case)}\n\n"
            f"{self._mock_outreach_product_line(product_focus=product_focus, variant=variant, use_case=use_case)}\n\n"
            f"{self._mock_outreach_cta(variant=variant, institution_name=institution_name, custom_note=custom_note)}\n\n"
            f"{ol_sig}\n"
        )
        return DraftResult(
            text=draft,
            provider_name="mock",
            abstained=False,
            notes=f"mock_template_origenlab_marketing_outreach:{variant}",
        )

    def generate(self, prompt_blocks: dict[str, object]) -> DraftResult:
        case = dict(prompt_blocks.get("case") or {})
        subject = str(case.get("subject") or "").strip()
        body = str(case.get("body_text") or "").strip()
        if len(body) < 40:
            return DraftResult(
                text="",
                provider_name="mock",
                abstained=True,
                notes="insufficient_context_body_too_short",
            )
        profile = str(prompt_blocks.get("drafting_profile") or "")
        ol_sig = str(prompt_blocks.get("approved_signature_block") or "").strip()
        if profile == DRAFTING_PROFILE_ORIGENLAB and ol_sig:
            if prompt_blocks.get("marketing_outreach_supplement"):
                return self._build_mock_outreach(
                    prompt_blocks=prompt_blocks,
                    subject=subject,
                    ol_sig=ol_sig,
                )
            draft = (
                f"Asunto: Re: {subject or 'Consulta'}\n\n"
                "Estimado/a,\n\n"
                "Gracias por contactarnos.\n\n"
                "Le confirmamos recepción de su consulta y compartimos esta respuesta preliminar según "
                "los datos indicados.\n\n"
                "Quedo atenta a sus comentarios o necesidad de información adicional.\n\n"
                f"{ol_sig}\n"
            )
            return DraftResult(
                text=draft,
                provider_name="mock",
                abstained=False,
                notes="mock_template_origenlab_mode",
            )
        draft = (
            f"Asunto: Re: {subject or 'Consulta'}\n\n"
            "Estimado/a,\n\n"
            "Gracias por contactarnos.\n\n"
            "Junto con saludar, y de acuerdo con la información compartida, le adjunto una propuesta inicial.\n"
            "Si me confirma cantidad, especificación técnica y plazo objetivo, le envío versión final cerrada.\n\n"
            "Quedo atenta a sus comentarios o consultas.\n\n"
            "Saludos cordiales,\n"
            "Tatiana Vivanco\n"
        )
        return DraftResult(
            text=draft,
            provider_name="mock",
            abstained=False,
            notes="mock_template_from_prompt_package",
        )
