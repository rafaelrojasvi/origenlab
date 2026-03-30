from __future__ import annotations

from origenlab_email_pipeline.config import Settings, load_settings

from .generator import DraftGenerator, MockDraftGenerator
from .openai_chat_generator import OpenAIChatDraftGenerator, TatianaLLMConfigurationError


def resolve_draft_generator(name: str, *, settings: Settings | None = None) -> DraftGenerator:
    """
    Select a DraftGenerator by CLI name.

    - mock: offline MockDraftGenerator
    - openai_chat (aliases: openai, llm): OpenAI Chat Completions; requires API key
    """
    key = (name or "mock").strip().lower()
    s = settings or load_settings()
    if key in ("mock", "none", "offline"):
        return MockDraftGenerator()
    if key in ("openai_chat", "openai", "llm"):
        return OpenAIChatDraftGenerator.from_settings(s)
    raise ValueError(f"Unknown --generator {name!r}; use mock or openai_chat.")


__all__ = [
    "OpenAIChatDraftGenerator",
    "TatianaLLMConfigurationError",
    "resolve_draft_generator",
]
