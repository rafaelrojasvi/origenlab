from __future__ import annotations

from dataclasses import dataclass


REVIEWER_DECISIONS = {"accept", "edit_light", "edit_heavy", "reject"}


def parse_score_1_5(v: str | None) -> int | None:
    s = (v or "").strip()
    if not s:
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    if 1 <= n <= 5:
        return n
    return None


def parse_decision(v: str | None) -> str | None:
    s = (v or "").strip().lower()
    if not s:
        return None
    return s if s in REVIEWER_DECISIONS else None


@dataclass(frozen=True)
class ReviewRow:
    eval_case_id: str
    label_expected: str
    abstained: bool
    reviewer_score_tone: int | None
    reviewer_score_usefulness: int | None
    reviewer_score_groundedness: int | None
    reviewer_score_edit_distance_estimate: int | None
    reviewer_decision: str | None
    notes: str
    system_notes: str

    @property
    def is_scored(self) -> bool:
        return any(
            x is not None
            for x in (
                self.reviewer_score_tone,
                self.reviewer_score_usefulness,
                self.reviewer_score_groundedness,
                self.reviewer_score_edit_distance_estimate,
            )
        ) or (self.reviewer_decision is not None)
