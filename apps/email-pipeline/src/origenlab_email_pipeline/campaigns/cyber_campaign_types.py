"""Shared types and segment constants for Cyber outreach (no cross-imports)."""

from __future__ import annotations

from dataclasses import dataclass

CYBER_CAMPAIGN_SLUG = "cyber_lab_equipment_cl_2026"

SEGMENT_WARM = "warm_open"
SEGMENT_PREVIOUS = "previous_buyer_responder"
SEGMENT_NET_NEW = "net_new_safe"
SEGMENT_SAME_DOMAIN = "same_domain_review"
SEGMENT_EXCLUDED = "excluded_blocked"
SEGMENT_NET_NEW_LEAD_RESEARCH = "net_new_lead_research"

SAFETY_ELIGIBLE = "eligible"
SAFETY_SAME_DOMAIN = "same_domain_review"
SAFETY_BLOCKED = "blocked"

OPT_OUT_LINE_ES = (
    "Si prefiere no recibir información comercial de OrigenLab, puede responder 'remover'."
)

CSV_FIELDS: tuple[str, ...] = (
    "email",
    "organization",
    "contact_name",
    "segment",
    "reason_for_inclusion",
    "product_angle",
    "suggested_subject",
    "suggested_message",
    "safety_status",
    "exclusion_reason",
)


@dataclass(frozen=True)
class CyberCampaignRow:
    email: str
    organization: str
    contact_name: str
    segment: str
    reason_for_inclusion: str
    product_angle: str
    suggested_subject: str
    suggested_message: str
    safety_status: str
    exclusion_reason: str
    priority_score: float = 0.0

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "organization": self.organization,
            "contact_name": self.contact_name,
            "segment": self.segment,
            "reason_for_inclusion": self.reason_for_inclusion,
            "product_angle": self.product_angle,
            "suggested_subject": self.suggested_subject,
            "suggested_message": self.suggested_message,
            "safety_status": self.safety_status,
            "exclusion_reason": self.exclusion_reason,
        }
