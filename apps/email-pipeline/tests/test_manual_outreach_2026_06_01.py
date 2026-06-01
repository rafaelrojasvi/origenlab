"""Tests for 2026-06-01 manual outreach registry and failure_type helpers."""

from __future__ import annotations

from origenlab_email_pipeline.campaigns.manual_outreach_2026_06_01 import (
    CYBER_BCC_BOUNCED_EXPECTED,
    CYBER_BCC_RECIPIENTS,
    MANUAL_PROSPECT_ROWS,
)
from origenlab_email_pipeline.campaigns.manual_outreach_failure_types import classify_failure_type


def test_manual_prospect_count() -> None:
    assert len(MANUAL_PROSPECT_ROWS) == 9


def test_hannelore_is_bounced_not_delivered() -> None:
    row = next(r for r in MANUAL_PROSPECT_ROWS if r.email == "hannelore.valentin@sgs.com")
    assert row.kind == "bounced_expected"
    assert row.expected_failure_type == "no_such_user"


def test_cyber_bcc_recipient_count() -> None:
    assert len(CYBER_BCC_RECIPIENTS) == 17


def test_failure_type_no_such_user() -> None:
    assert classify_failure_type("550 5.1.1 User unknown") == "no_such_user"


def test_failure_type_group_permission() -> None:
    assert (
        classify_failure_type("You do not have permission to post to this Google group")
        == "group_or_permission"
    )


def test_failure_type_domain_not_found() -> None:
    assert classify_failure_type("Domain mrlab.cl not found") == "domain_not_found"


def test_cyber_bounced_subset_of_recipients() -> None:
    assert CYBER_BCC_BOUNCED_EXPECTED <= frozenset(CYBER_BCC_RECIPIENTS)
