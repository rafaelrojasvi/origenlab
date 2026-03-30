from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PilotInputCase:
    """One real candidate row for a pilot batch (no LLM fields)."""

    case_id: str
    subject: str
    body_text: str
    from_email: str | None = None
    from_name: str | None = None
    thread_hint: str | None = None
    received_at: str | None = None
    case_type: str | None = None  # expected_mode / label hint; nullable
    notes: str | None = None
    # Current-company pilot fields (optional; flow to context_metadata for OrigenLab mode)
    requester_name: str | None = None
    requester_email: str | None = None
    requested_product_or_category: str | None = None
    explicit_known_facts: str | None = None
    missing_information: str | None = None
    notes_for_reviewer: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def context_metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "pilot": True,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "thread_hint": self.thread_hint,
            "received_at": self.received_at,
            "case_type": self.case_type,
            "notes": self.notes,
            "requester_name": self.requester_name,
            "requester_email": self.requester_email,
            "requested_product_or_category": self.requested_product_or_category,
            "explicit_known_facts": self.explicit_known_facts,
            "missing_information": self.missing_information,
            "notes_for_reviewer": self.notes_for_reviewer,
        }
        meta.update(self.extra)
        return {k: v for k, v in meta.items() if v not in (None, "", [])}


def safe_case_filename(case_id: str) -> str:
    s = (case_id or "case").strip() or "case"
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE).strip("._") or "case"
    return s[:120]


def text_preview(text: str, *, max_chars: int = 400) -> str:
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3].rstrip() + "..."


def extract_asunto_from_draft(draft: str) -> str:
    lines = (draft or "").strip().splitlines()
    if not lines:
        return ""
    first = lines[0].strip()
    if first.lower().startswith("asunto:"):
        return first.split(":", 1)[1].strip()
    return ""


# Human review CSV: machine-generated + reviewer columns (reviewer columns start empty).
PILOT_REVIEW_MACHINE_FIELDS: tuple[str, ...] = (
    "case_id",
    "subject_input",
    "body_preview",
    "generated_subject",
    "generated_body",
    "abstained",
    "provider_name",
    "retrieved_style_ids",
    "retrieved_example_ids",
    "system_notes",
)

PILOT_REVIEW_REVIEWER_FIELDS: tuple[str, ...] = (
    "reviewer_decision",
    "reviewer_edit_level",
    "reviewer_sentiment",
    "reviewer_notes",
    "reviewer_final_subject",
    "reviewer_final_body",
    "approved_for_send",
)

PILOT_REVIEW_ALL_FIELDS: tuple[str, ...] = PILOT_REVIEW_MACHINE_FIELDS + PILOT_REVIEW_REVIEWER_FIELDS

# Suggested enums (documentation / validation in summarizer only where strict).
VALID_REVIEWER_DECISIONS = frozenset(
    {"approve", "approve_with_edits", "reject", "needs_clarification", ""}
)
VALID_EDIT_LEVELS = frozenset({"none", "light", "moderate", "heavy", ""})
VALID_SENTIMENT = frozenset({"good", "mixed", "poor", ""})
VALID_APPROVED_FOR_SEND = frozenset({"y", "n", ""})


def sentiment_numeric(s: str | None) -> int | None:
    if not (s or "").strip():
        return None
    k = s.strip().lower()
    if k == "good":
        return 3
    if k == "mixed":
        return 2
    if k == "poor":
        return 1
    return None
