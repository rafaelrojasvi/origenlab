from __future__ import annotations

from typing import TYPE_CHECKING

from .generator import DraftGenerator, MockDraftGenerator
from .index import TatianaExampleIndex
from .origenlab_context import DRAFTING_PROFILE_TATIANA_HISTORICAL
from .prompting import DEFAULT_GUARDRAILS, build_prompt_blocks
from .retrieve import retrieve_for_case
from .schemas import DraftCase, DraftPackage

if TYPE_CHECKING:
    from .origenlab_context import OrigenLabDraftingContext


def build_draft_package(
    *,
    case: DraftCase,
    index: TatianaExampleIndex,
    generator: DraftGenerator | None = None,
    style_top_k: int = 3,
    retrieval_top_k: int = 5,
    exclude_example_ids: set[str] | None = None,
    drafting_profile: str = DRAFTING_PROFILE_TATIANA_HISTORICAL,
    origenlab_context: OrigenLabDraftingContext | None = None,
) -> DraftPackage:
    gen = generator or MockDraftGenerator()
    style, similar = retrieve_for_case(
        index=index,
        query_text=f"Subject: {case.subject}\n{case.body_text}",
        style_top_k=style_top_k,
        retrieval_top_k=retrieval_top_k,
        exclude_example_ids=exclude_example_ids,
    )
    blocks = build_prompt_blocks(
        case=case,
        style_examples=style,
        retrieved_examples=similar,
        drafting_profile=drafting_profile,
        origenlab_context=origenlab_context,
    )
    guardrails = list(blocks.get("guardrails") or DEFAULT_GUARDRAILS)
    result = gen.generate(blocks)
    return DraftPackage(
        case=case.to_dict(),
        retrieved_examples=[x.to_dict() for x in similar],
        retrieved_style_examples=[x.to_dict() for x in style],
        guardrails=guardrails,
        prompt_blocks=blocks,
        generated_draft=result.text,
        provider_name=result.provider_name,
        abstained=result.abstained,
        notes=result.notes,
    )
