from __future__ import annotations

from dataclasses import dataclass

from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB


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
