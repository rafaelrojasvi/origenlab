from __future__ import annotations

from typing import TYPE_CHECKING

from .marketing_outreach import is_marketing_outreach_case, marketing_outreach_supplement
from .schemas import DraftCase, RetrievedExample

if TYPE_CHECKING:
    from .origenlab_context import OrigenLabDraftingContext

from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB, DRAFTING_PROFILE_TATIANA_HISTORICAL

DEFAULT_GUARDRAILS = [
    "Human approval required before sending.",
    "Do not invent pricing, stock, lead times, specs, or guarantees.",
    "Use retrieved examples for tone/structure, not as factual truth.",
    "If case context is insufficient, abstain and request missing details.",
    "Prefer concise, commercially useful Spanish prose.",
    "No hidden side effects: drafting only, no sending.",
]

ORIGENLAB_EXTRA_GUARDRAILS = [
    "OrigenLab mode: company_facts and commercial_policy are approved positioning and rules; "
    "do not substitute Labdelivery or any legacy signature.",
    "Historical retrieved emails are style/reference only, not identity or commercial truth.",
    "For marketing outreach, personalize only with confirmed fields supplied in the case metadata; "
    "do not invent recipient facts, installed base, purchase plans, or sector-specific needs.",
]


def build_prompt_blocks(
    *,
    case: DraftCase,
    style_examples: list[RetrievedExample],
    retrieved_examples: list[RetrievedExample],
    drafting_profile: str = DRAFTING_PROFILE_TATIANA_HISTORICAL,
    origenlab_context: OrigenLabDraftingContext | None = None,
) -> dict[str, object]:
    style_block = [
        {
            "role": "STYLE_REFERENCE_ONLY_NOT_FACTS",
            "example_id": e.example_id,
            "label": e.label,
            "subject": e.subject,
            "body_text": e.body_text[:700],
        }
        for e in style_examples
    ]
    precedent_block = [
        {
            "role": "STYLE_REFERENCE_ONLY_NOT_FACTS",
            "example_id": e.example_id,
            "label": e.label,
            "subject": e.subject,
            "body_text": e.body_text[:700],
        }
        for e in retrieved_examples
    ]

    meta = dict(case.context_metadata or {})
    case_supplement = {
        "requester_name": meta.get("requester_name"),
        "requester_email": meta.get("requester_email"),
        "requested_product_or_category": meta.get("requested_product_or_category"),
        "explicit_known_facts": meta.get("explicit_known_facts"),
        "missing_information": meta.get("missing_information"),
        "notes_for_reviewer": meta.get("notes_for_reviewer"),
    }
    case_supplement = {k: v for k, v in case_supplement.items() if v not in (None, "", [])}
    outreach_mode = is_marketing_outreach_case(meta, case.expected_label)
    outreach_supplement = marketing_outreach_supplement(meta) if outreach_mode else {}

    if drafting_profile == DRAFTING_PROFILE_ORIGENLAB:
        if origenlab_context is None:
            raise ValueError("origenlab_context is required when drafting_profile is origenlab")
        if outreach_mode:
            instruction = (
                "Draft a first-touch B2B marketing / presentation email in Spanish (Chile) as OrigenLab. "
                "This is commercial outreach, not support or a transactional reply. "
                "Use company_facts for approved identity, contact details, and high-level positioning. "
                "Use commercial_policy as hard constraints. "
                "Use marketing_outreach_supplement for the canonical base presentation email, requested variant, "
                "canonical sender identity, approved signature block, and confirmed personalization fields. "
                "Personalize only with those confirmed fields; "
                "if a field is absent, keep the draft generic rather than inventing details. "
                "Use style_examples and retrieved_precedents ONLY for tone, courtesy, and paragraph structure; "
                "never copy legacy signatures, phones, domains, or factual claims from them. "
                "The output should be polished, commercially credible, and have a clear CTA, while staying honest "
                "about products and use cases. Commercial and technical claims must come only from case.body_text, "
                "marketing_outreach_supplement, case_context_supplement, or company_facts. "
                "Do not output placeholders such as [Tu Nombre], [Nombre], [Institucion], <...>, or {{...}}. "
                "If no sender field is supplied, use the canonical sender identity from marketing_outreach_supplement "
                "and the approved signature block exactly. "
                "If essential facts are missing, output exactly ABSTAIN on one line."
            )
        else:
            instruction = (
                "Draft a B2B commercial email in Spanish (Chile) as OrigenLab — not as Labdelivery or any "
                "historical alias. Use company_facts for approved identity, contact, and positioning. "
                "Use commercial_policy as hard constraints. "
                "Use case_context_supplement for confirmed facts and gaps (explicit_known_facts, missing_information). "
                "Use style_examples and retrieved_precedents ONLY for tone, greeting patterns, and paragraph structure; "
                "never copy legacy signatures, phones, domains, or factual claims from them. "
                "Commercial and technical claims must come only from case.body_text, case_context_supplement, "
                "or company_facts (for high-level approved positioning). "
                "If essential facts are missing, output exactly ABSTAIN on one line."
            )
        company_facts = origenlab_context.company_facts_dict()
        policy = list(origenlab_context.commercial_policy_bullets)
        approved_signature = origenlab_context.approved_signature_block
        guardrails = list(DEFAULT_GUARDRAILS) + list(ORIGENLAB_EXTRA_GUARDRAILS)
        return {
            "drafting_profile": drafting_profile,
            "instruction": instruction,
            "guardrails": guardrails,
            "company_facts": company_facts,
            "commercial_policy": policy,
            "case_context_supplement": case_supplement,
            "marketing_outreach_supplement": outreach_supplement,
            "style_reference_notice": (
                "Ejemplos recuperados = solo estilo (tono, cortesía, estructura). "
                "No son hechos ni identidad comercial vigente."
            ),
            "approved_signature_block": approved_signature,
            "case": case.to_dict(),
            "style_examples": style_block,
            "retrieved_precedents": precedent_block,
            "origenlab_fact_sources": list(origenlab_context.fact_sources),
        }

    instruction = (
        "Draft a reply in Tatiana-style commercial Spanish (historical / cohort reference voice). "
        "Use style patterns from style examples and factual context only from case input. "
        "Examples are style-only, not factual truth. "
        "If core details are missing, abstain."
    )
    return {
        "drafting_profile": drafting_profile,
        "instruction": instruction,
        "guardrails": list(DEFAULT_GUARDRAILS),
        "case": case.to_dict(),
        "style_examples": [
            {k: v for k, v in x.items() if k != "role"} for x in style_block
        ],
        "retrieved_precedents": [
            {k: v for k, v in x.items() if k != "role"} for x in precedent_block
        ],
    }
