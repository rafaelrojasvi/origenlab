from __future__ import annotations

import pytest

from origenlab_email_pipeline.candidate_export_gate import (
    REASON_INTERNAL_DOMAIN,
    REASON_INVALID_EMAIL,
    REASON_NOISE_EMAIL,
    REASON_NOISE_ORGANIZATION,
    REASON_OUTREACH_CONTACTED,
    REASON_OUTREACH_REPLIED,
    REASON_OUTREACH_SNOOZED,
    REASON_SENT_HISTORY,
    REASON_SUPPLIER_DOMAIN,
    REASON_SUPPRESSION,
    ExportGateResult,
    GateContext,
    evaluate_export_eligibility,
)


def _ctx(**kwargs) -> GateContext:
    base = dict(
        sent_recipient_norms=frozenset(),
        suppressed_norms=frozenset(),
        outreach_state_by_email={},
        supplier_domains=frozenset(),
        blocked_domains=frozenset({"origenlab.cl", "labdelivery.cl"}),
        skip_noise_filter=False,
        skip_supplier_domain_filter=False,
    )
    base.update(kwargs)
    return GateContext(**base)


def test_supplier_domain_blocks() -> None:
    ctx = _ctx(supplier_domains=frozenset({"ohaus.com"}))
    r = evaluate_export_eligibility(contact_email="x@ohaus.com", institution_name="Ohaus", ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_SUPPLIER_DOMAIN,))


def test_supplier_skipped_when_flag_set() -> None:
    ctx = _ctx(
        supplier_domains=frozenset({"ohaus.com"}),
        skip_supplier_domain_filter=True,
    )
    r = evaluate_export_eligibility(contact_email="x@ohaus.com", institution_name=None, ctx=ctx)
    assert r.eligible is True


def test_noise_email_blocks() -> None:
    ctx = _ctx()
    r = evaluate_export_eligibility(contact_email="noreply@cliente.cl", institution_name="ACME", ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_NOISE_EMAIL,))


def test_noise_org_blocks() -> None:
    ctx = _ctx()
    r = evaluate_export_eligibility(contact_email="a@example.cl", institution_name="DHL Express", ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_NOISE_ORGANIZATION,))


def test_suppression_blocks() -> None:
    ctx = _ctx(suppressed_norms=frozenset({"a@b.cl"}))
    r = evaluate_export_eligibility(contact_email="a@b.cl", institution_name=None, ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_SUPPRESSION,))


def test_sent_history_blocks() -> None:
    ctx = _ctx(sent_recipient_norms=frozenset({"a@b.cl"}))
    r = evaluate_export_eligibility(contact_email="a@b.cl", institution_name=None, ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_SENT_HISTORY,))


def test_internal_domain_blocks() -> None:
    ctx = _ctx()
    r = evaluate_export_eligibility(contact_email="x@origenlab.cl", institution_name=None, ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(REASON_INTERNAL_DOMAIN,))


@pytest.mark.parametrize(
    "state,expected_reason",
    [
        ("contacted", REASON_OUTREACH_CONTACTED),
        ("replied", REASON_OUTREACH_REPLIED),
        ("snoozed", REASON_OUTREACH_SNOOZED),
    ],
)
def test_outreach_states_block(state: str, expected_reason: str) -> None:
    ctx = _ctx(outreach_state_by_email={"buyer@uni.cl": state})
    r = evaluate_export_eligibility(contact_email="buyer@uni.cl", institution_name="Uni", ctx=ctx)
    assert r == ExportGateResult(eligible=False, reasons=(expected_reason,))


def test_not_contacted_outreach_does_not_block() -> None:
    ctx = _ctx(outreach_state_by_email={"buyer@uni.cl": "not_contacted"})
    r = evaluate_export_eligibility(contact_email="buyer@uni.cl", institution_name="Uni", ctx=ctx)
    assert r.eligible is True


def test_evaluation_order_suppression_before_sent() -> None:
    ctx = _ctx(
        suppressed_norms=frozenset({"a@b.cl"}),
        sent_recipient_norms=frozenset({"a@b.cl"}),
    )
    r = evaluate_export_eligibility(contact_email="a@b.cl", institution_name=None, ctx=ctx)
    assert r.reasons == (REASON_SUPPRESSION,)


def test_parity_same_email_and_org_same_result() -> None:
    ctx = _ctx(supplier_domains=frozenset({"ohaus.com"}), sent_recipient_norms=frozenset({"x@y.cl"}))
    r1 = evaluate_export_eligibility(contact_email="lab@ohaus.com", institution_name="Lab", ctx=ctx)
    r2 = evaluate_export_eligibility(contact_email="lab@ohaus.com", institution_name="Lab", ctx=ctx)
    assert r1 == r2 == ExportGateResult(eligible=False, reasons=(REASON_SUPPLIER_DOMAIN,))


@pytest.mark.parametrize(
    "email,org,expect_eligible",
    [
        ("scientist@universidad.cl", "Universidad de Chile", True),
        ("", None, False),
        ("not-an-email", None, False),
    ],
)
def test_regression_known_good_bad(email: str, org: str | None, expect_eligible: bool) -> None:
    ctx = _ctx()
    r = evaluate_export_eligibility(contact_email=email, institution_name=org, ctx=ctx)
    if expect_eligible:
        assert r.eligible is True
    else:
        assert r.eligible is False
        assert r.reasons and r.reasons[0] == REASON_INVALID_EMAIL
