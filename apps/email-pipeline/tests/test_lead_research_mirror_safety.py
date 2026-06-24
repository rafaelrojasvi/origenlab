"""Tests for lead_research mirror text safety (Gmail URL parsing)."""

from __future__ import annotations

import pytest

from origenlab_email_pipeline.lead_research.lead_research_mirror_safety import (
    LeadResearchMirrorSafetyError,
    assert_mirror_text_safe,
)


def test_assert_mirror_text_safe_rejects_gmail_mailbox_urls() -> None:
    with pytest.raises(LeadResearchMirrorSafetyError, match="forbidden gmail URL"):
        assert_mirror_text_safe(
            "Evidence: https://mail.google.com/mail/u/0/#inbox/abc",
            field="lead_intel.prospect.evidence_note",
        )
    with pytest.raises(LeadResearchMirrorSafetyError, match="forbidden gmail URL"):
        assert_mirror_text_safe(
            "https://accounts.google.com/mail/u/1/?tab=rm",
            field="lead_intel.prospect.evidence_url",
        )


def test_assert_mirror_text_safe_allows_non_gmail_mentions() -> None:
    assert_mirror_text_safe(
        "Operator noted mail.google.com access is out of scope for mirror.",
        field="lead_intel.prospect.evidence_note",
    )
    assert_mirror_text_safe(
        "Hostname mail.google.com.evil.test is not a Gmail mailbox host.",
        field="lead_intel.prospect.evidence_note",
    )
    assert_mirror_text_safe(
        "Query-only mention /mail/u/0 in prose without a Google URL.",
        field="lead_intel.prospect.evidence_note",
    )
    assert_mirror_text_safe(
        "https://evil.test/?next=/mail/u/0",
        field="lead_intel.prospect.evidence_url",
    )
