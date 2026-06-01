"""Types for read-only Presentación OrigenLab review lists (no sends)."""

from __future__ import annotations

from dataclasses import dataclass

PRESENTACION_CAMPAIGN_SLUG = "presentacion_origenlab_cyber_suave_2026"

BUCKET_SEND_NOW = "send_now_review"
BUCKET_SAME_DOMAIN = "same_domain_review"
BUCKET_HOLD_ACTIVE = "hold_active_case"
BUCKET_MISSING_EMAIL = "missing_email_research"

ACTION_SEND_NOW_REVIEW = "operator_review_before_send"
ACTION_REVIEW_HISTORY_ONLY = "review_history_only_no_auto_send"
ACTION_HOLD_ACTIVE = "hold_active_case_no_campaign"
ACTION_RESEARCH_CONTACT = "research_contact_first"

REVIEW_CSV_FIELDS: tuple[str, ...] = (
    "email",
    "organization",
    "contact_name",
    "bucket",
    "reason_for_inclusion",
    "product_angle",
    "history_note",
    "suggested_subject",
    "suggested_message",
    "recommended_action",
    "priority_score",
    "exclusion_flags",
)


@dataclass(frozen=True)
class PresentacionReviewRow:
    email: str
    organization: str
    contact_name: str
    bucket: str
    reason_for_inclusion: str
    product_angle: str
    history_note: str
    suggested_subject: str
    suggested_message: str
    recommended_action: str
    priority_score: float = 0.0
    exclusion_flags: str = ""

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "organization": self.organization,
            "contact_name": self.contact_name,
            "bucket": self.bucket,
            "reason_for_inclusion": self.reason_for_inclusion,
            "product_angle": self.product_angle,
            "history_note": self.history_note,
            "suggested_subject": self.suggested_subject,
            "suggested_message": self.suggested_message,
            "recommended_action": self.recommended_action,
            "priority_score": f"{self.priority_score:.1f}",
            "exclusion_flags": self.exclusion_flags,
        }
