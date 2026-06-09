"""Pure helpers to compute per-email mart features (not wired into build-mart yet)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from origenlab_email_pipeline.business_mart import (
    classify_email_intents,
    domain_of,
    emails_in,
    equipment_tags_from_text,
    is_noise_sender,
    primary_sender_email,
)
from origenlab_email_pipeline.freshness_dates import email_date_iso_for_mart_timeline

FEATURE_VERSION = "v1"


@dataclass(frozen=True)
class EmailMartFeature:
    email_id: int
    message_id: str | None
    source_file: str | None
    folder: str | None
    sender_email: str | None
    sender_domain: str | None
    recipient_emails_json: str
    external_targets_json: str
    direction: str
    is_noise: int
    is_quote_email: int
    is_invoice_email: int
    is_purchase_email: int
    equipment_tags_json: str
    mart_date_iso: str | None
    body_len: int
    feature_source_hash: str
    computed_at: str


def select_mart_body_text(top_reply_clean: str | None, full_body_clean: str | None) -> str:
    top = top_reply_clean or ""
    if top:
        return top
    return full_body_clean or ""


def compute_feature_source_hash(
    *,
    message_id: str | None,
    sender: str | None,
    recipients: str | None,
    subject: str | None,
    top_reply_clean: str | None,
    full_body_clean: str | None,
    date_iso: str | None,
    internal_domains: frozenset[str] | set[str],
    mart_date_slack_days: int,
) -> str:
    payload = {
        "v": FEATURE_VERSION,
        "message_id": message_id or "",
        "sender": sender or "",
        "recipients": recipients or "",
        "subject": subject or "",
        "top_reply_clean": top_reply_clean or "",
        "full_body_clean": full_body_clean or "",
        "date_iso": date_iso or "",
        "internal_domains": sorted(internal_domains),
        "mart_date_slack_days": int(mart_date_slack_days),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_string_list(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"))


def _build_external_targets(
    *,
    direction: str,
    outbound: bool,
    inbound: bool,
    sender_email: str | None,
    sender_dom: str,
    recip_emails: list[str],
    internal_domains: set[str],
) -> list[str]:
    targets: list[str] = []
    if outbound:
        for email in recip_emails:
            dom = domain_of(email) or ""
            if dom and dom not in internal_domains:
                targets.append(email)
    elif inbound and sender_email:
        if sender_dom and sender_dom not in internal_domains:
            targets.append(sender_email)
    return targets


def compute_email_mart_feature(
    *,
    email_id: int,
    message_id: str | None,
    source_file: str | None,
    folder: str | None,
    sender: str | None,
    recipients: str | None,
    subject: str | None,
    top_reply_clean: str | None,
    full_body_clean: str | None,
    date_iso: str | None,
    internal_domains: frozenset[str] | set[str],
    mart_date_slack_days: int,
    computed_at: str | None = None,
) -> EmailMartFeature:
    internal = set(internal_domains)
    sender_s = sender or ""
    subj = subject or ""
    body = select_mart_body_text(top_reply_clean, full_body_clean)

    sender_email = primary_sender_email(sender_s) or None
    sender_dom = domain_of(sender_email) or "" if sender_email else ""
    recip_emails = emails_in(recipients or "")

    outbound = bool(sender_dom) and sender_dom in internal
    inbound = bool(sender_dom) and not outbound
    if outbound:
        direction = "outbound"
    elif inbound:
        direction = "inbound"
    else:
        direction = "other"

    external_targets = _build_external_targets(
        direction=direction,
        outbound=outbound,
        inbound=inbound,
        sender_email=sender_email,
        sender_dom=sender_dom,
        recip_emails=recip_emails,
        internal_domains=internal,
    )

    noise = is_noise_sender(sender_s, subj, body)
    intents = classify_email_intents(subj, body)
    equip = equipment_tags_from_text(subj + "\n" + body)
    mart_date = email_date_iso_for_mart_timeline(date_iso, slack_days=mart_date_slack_days)

    stamp = computed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return EmailMartFeature(
        email_id=int(email_id),
        message_id=message_id,
        source_file=source_file,
        folder=folder,
        sender_email=sender_email,
        sender_domain=sender_dom or None,
        recipient_emails_json=_json_string_list(recip_emails),
        external_targets_json=_json_string_list(external_targets),
        direction=direction,
        is_noise=1 if noise else 0,
        is_quote_email=1 if intents["is_quote_email"] else 0,
        is_invoice_email=1 if intents["is_invoice_email"] else 0,
        is_purchase_email=1 if intents["is_purchase_email"] else 0,
        equipment_tags_json=_json_string_list(sorted(equip)),
        mart_date_iso=mart_date,
        body_len=len(body),
        feature_source_hash=compute_feature_source_hash(
            message_id=message_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            top_reply_clean=top_reply_clean,
            full_body_clean=full_body_clean,
            date_iso=date_iso,
            internal_domains=internal_domains,
            mart_date_slack_days=mart_date_slack_days,
        ),
        computed_at=stamp,
    )
