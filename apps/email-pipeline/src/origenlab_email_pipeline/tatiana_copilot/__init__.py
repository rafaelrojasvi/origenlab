"""Tatiana drafting copilot (review-first, local-first)."""

from .draft_package import build_draft_package
from .generator import MockDraftGenerator
from .generator_factory import (
    OpenAIChatDraftGenerator,
    TatianaLLMConfigurationError,
    resolve_draft_generator,
)
from .index import TatianaExampleIndex
from .loader import load_csv_rows
from .normalize import build_example_sets
from .schemas import DraftCase, DraftPackage, ExampleRecord

__all__ = [
    "DraftCase",
    "DraftPackage",
    "ExampleRecord",
    "MockDraftGenerator",
    "OpenAIChatDraftGenerator",
    "TatianaExampleIndex",
    "TatianaLLMConfigurationError",
    "build_draft_package",
    "build_example_sets",
    "load_csv_rows",
    "resolve_draft_generator",
]
