from __future__ import annotations

from dataclasses import asdict, dataclass, field


# Prompt / package profiles (backward compatible default: historical Tatiana).
DRAFTING_PROFILE_TATIANA_HISTORICAL = "tatiana_historical"
DRAFTING_PROFILE_ORIGENLAB = "origenlab"


@dataclass(frozen=True)
class OrigenLabDraftingContext:
    """
    Canonical facts and policy boundaries for OrigenLab-native drafting.

    Historical Tatiana / archive examples are never part of this object — they remain
    style-only blocks in the prompt package (see prompting.build_prompt_blocks).
    """

    company_name: str
    geography: str
    base_location: str
    positioning_one_liner: str
    catalog_note: str
    audience_lines: tuple[str, ...]
    contact_email: str
    contact_phone: str
    location_public: str
    hours: str
    services_summary: str
    categories_summary: str
    brands_products_summary: str
    commercial_policy_bullets: tuple[str, ...]
    approved_signature_block: str
    fact_sources: tuple[str, ...] = field(default_factory=tuple)

    def company_facts_dict(self) -> dict[str, str]:
        return {
            "company_name": self.company_name,
            "geography": self.geography,
            "base_location": self.base_location,
            "positioning_one_liner": self.positioning_one_liner,
            "catalog_note": self.catalog_note,
            "audience": " · ".join(self.audience_lines),
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "location_public": self.location_public,
            "public_hours": self.hours,
            "services_summary": self.services_summary,
            "product_lines_summary": self.categories_summary,
            "catalog_brands_products": self.brands_products_summary,
        }

    def to_serializable_summary(self) -> dict[str, object]:
        return {
            "kind": "origenlab_drafting_context",
            "company_facts": self.company_facts_dict(),
            "commercial_policy": list(self.commercial_policy_bullets),
            "approved_signature_block": self.approved_signature_block,
            "fact_sources": list(self.fact_sources),
        }


def default_commercial_policy_bullets() -> tuple[str, ...]:
    """
    Short policy mirror of repo `docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`.
    Do not restate the full doc; loaders point humans to that file.
    """
    return (
        "No afirmar marcas, garantías, stock, plazos, especificaciones técnicas, SLAs, "
        "exclusividad ni alianzas salvo que consten en el texto del caso o en explicit_known_facts "
        "como hecho confirmado.",
        "Precios, condiciones comerciales y plazos: solo si el caso o explicit_known_facts los entregan "
        "explícitamente; si no, usar formulaciones neutras o indicar datos pendientes.",
        "Instalación / puesta en marcha: solo en la forma acordada en el caso o política aprobada "
        "(alcance por escrito); no prometer cobertura no confirmada.",
        "Los ejemplos de estilo (archivo Tatiana/cohort) son referencia de tono y estructura, "
        "no fuente de hechos ni de identidad comercial actual.",
        "Si falta información esencial para una respuesta comercial segura, abstenerse (ABSTAIN).",
    )
