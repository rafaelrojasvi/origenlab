"""Extended CSV fields for Presentación OrigenLab quality-pass outputs."""

from __future__ import annotations

from dataclasses import dataclass

CLASS_PRESENTATION = "A_presentacion_empresa"
CLASS_FOLLOWUP_OLD = "B_followup_antiguo"
CLASS_HOLD_PERSONALIZED = "C_hold_activo_personalizado"
CLASS_SAME_DOMAIN = "D_same_domain_review"
CLASS_MISSING_EMAIL = "E_missing_email_research"
CLASS_EXCLUDED = "excluded"

BATCH_CSV_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "organization",
    "contact_name",
    "classification",
    "sector_guess",
    "reason_for_inclusion",
    "history_note",
    "product_angle",
    "suggested_subject",
    "suggested_message",
    "recommended_action",
    "priority_score",
    "dedupe_key",
    "primary_or_secondary",
)

HOLD_PERSONALIZED_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "organization",
    "contact_name",
    "case_label",
    "personalized_action",
    "history_note",
    "suggested_subject",
    "suggested_message",
    "recommended_action",
)

DO_NOT_SEND_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "organization",
    "reason_code",
    "reason_detail",
    "primary_chosen_email",
    "classification_attempted",
)

SAME_DOMAIN_CURATED_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "organization",
    "contact_name",
    "review_note",
    "product_angle",
    "recommended_action",
    "priority_score",
)


@dataclass(frozen=True)
class PresentacionBatchRow:
    email: str
    domain: str
    organization: str
    contact_name: str
    classification: str
    sector_guess: str
    reason_for_inclusion: str
    history_note: str
    product_angle: str
    suggested_subject: str
    suggested_message: str
    recommended_action: str
    priority_score: float = 0.0
    dedupe_key: str = ""
    primary_or_secondary: str = "primary"

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "domain": self.domain,
            "organization": self.organization,
            "contact_name": self.contact_name,
            "classification": self.classification,
            "sector_guess": self.sector_guess,
            "reason_for_inclusion": self.reason_for_inclusion,
            "history_note": self.history_note,
            "product_angle": self.product_angle,
            "suggested_subject": self.suggested_subject,
            "suggested_message": self.suggested_message,
            "recommended_action": self.recommended_action,
            "priority_score": f"{self.priority_score:.1f}",
            "dedupe_key": self.dedupe_key,
            "primary_or_secondary": self.primary_or_secondary,
        }


@dataclass(frozen=True)
class HoldPersonalizedRow:
    email: str
    domain: str
    organization: str
    contact_name: str
    case_label: str
    personalized_action: str
    history_note: str
    suggested_subject: str
    suggested_message: str
    recommended_action: str

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "domain": self.domain,
            "organization": self.organization,
            "contact_name": self.contact_name,
            "case_label": self.case_label,
            "personalized_action": self.personalized_action,
            "history_note": self.history_note,
            "suggested_subject": self.suggested_subject,
            "suggested_message": self.suggested_message,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class DoNotSendRow:
    email: str
    domain: str
    organization: str
    reason_code: str
    reason_detail: str
    primary_chosen_email: str
    classification_attempted: str

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "domain": self.domain,
            "organization": self.organization,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "primary_chosen_email": self.primary_chosen_email,
            "classification_attempted": self.classification_attempted,
        }
