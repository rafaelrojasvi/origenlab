from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExampleRecord:
    example_id: str
    source_file: str
    source_row_id: str
    kind: str  # style | retrieval
    label: str
    subject: str
    body_text: str
    search_text: str
    date_iso: str | None
    freshness_bucket: str | None
    language_signal: str | None
    contamination_signal: str | None
    keep_for_style_guide: bool
    keep_for_retrieval_later: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DraftCase:
    case_id: str
    subject: str
    body_text: str
    expected_label: str | None = None
    context_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedExample:
    example_id: str
    score: float
    label: str
    subject: str
    body_text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DraftPackage:
    case: dict[str, Any]
    retrieved_examples: list[dict[str, Any]]
    retrieved_style_examples: list[dict[str, Any]]
    guardrails: list[str]
    prompt_blocks: dict[str, Any]
    generated_draft: str
    provider_name: str
    abstained: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
