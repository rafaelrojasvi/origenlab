"""Tests for client report domain extraction (canonical ``emails_in``)."""

from __future__ import annotations

import pytest

from origenlab_email_pipeline.client_report_domains import primary_domain, recip_domains


def test_primary_domain_first_mailbox_domain_lowercased() -> None:
    assert primary_domain("Person <Contacto@Cliente.CL>") == "cliente.cl"


def test_primary_domain_no_address_placeholder() -> None:
    assert primary_domain("") == "(no address)"
    assert primary_domain("no email here") == "(no address)"


def test_recip_domains_multiple_and_lowercased() -> None:
    assert recip_domains("A@Foo.CL, b@bar.org") == ["foo.cl", "bar.org"]


def test_recip_domains_empty() -> None:
    assert recip_domains("") == []


@pytest.mark.parametrize(
    "sender",
    [
        "compras@hospitalregional.cl",
        "  Compras@HospitalRegional.CL  ",
    ],
)
def test_primary_domain_institutional_mailbox_allowed(sender: str) -> None:
    assert primary_domain(sender) == "hospitalregional.cl"


def test_recip_domains_preserves_order_and_dedupes_not_applied() -> None:
    """Same domain twice still appears twice (matches prior script behavior)."""
    assert recip_domains("x@lab.cl; y@lab.cl") == ["lab.cl", "lab.cl"]
