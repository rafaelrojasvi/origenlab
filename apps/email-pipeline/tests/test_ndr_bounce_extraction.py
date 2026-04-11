"""Tests for NDR recipient extraction and bounce code heuristics."""

from __future__ import annotations

from origenlab_email_pipeline.ndr_bounce_extraction import (
    bounce_suppression_code_from_ndr_text,
    extract_failed_recipients_from_ndr,
)


def test_final_recipient_rfc822():
    text = """
Reporting-MTA: dns; googlemail.com
Final-Recipient: rfc822; adquisiciones@usach.cl
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 The email account that you tried to reach does not exist.
"""
    assert extract_failed_recipients_from_ndr(text) == ["adquisiciones@usach.cl"]


def test_x_failed_recipients_google():
    text = """
X-Failed-Recipients: nayadeth@municunco.cl
Subject: Delivery Status Notification (Failure)
550 5.1.1 User unknown
"""
    assert "nayadeth@municunco.cl" in extract_failed_recipients_from_ndr(text)


def test_excludes_google_internal_mail_gmail():
    text = "Final-Recipient: rfc822; x+y@mail.gmail.com"
    assert extract_failed_recipients_from_ndr(text) == []


def test_excludes_origenlab_address():
    text = """
Final-Recipient: rfc822; contacto@origenlab.cl
Final-Recipient: rfc822; direccion@saludoriente.cl
"""
    assert extract_failed_recipients_from_ndr(text) == ["direccion@saludoriente.cl"]


def test_bounce_code_user_unknown():
    assert bounce_suppression_code_from_ndr_text("550 5.1.1 User unknown") == "bounce_no_such_user"


def test_bounce_code_policy():
    blob = "554 5.7.1 Message rejected due to policy. access denied relay"
    assert bounce_suppression_code_from_ndr_text(blob) == "bounce_access_denied"
