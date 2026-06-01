"""Tests for NDR recipient extraction and bounce code heuristics."""

from __future__ import annotations

from origenlab_email_pipeline.ndr_bounce_extraction import (
    bounce_suppression_code_from_ndr_text,
    extract_failed_recipients_from_ndr,
)

# --- Standard DSN headers (existing behavior) ---


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


# --- Gmail DSN templates (no Final-Recipient line) ---


def test_gmail_spanish_no_se_entrego_a():
    text = """
** No se encontró la dirección **
Tu mensaje no se entregó a snunez@valma.cl porque la dirección no se encuentra
o no puede recibir correos electrónicos.
"""
    assert extract_failed_recipients_from_ndr(text) == ["snunez@valma.cl"]


def test_gmail_english_wasnt_delivered_to():
    text = """
Address not found
Your message wasn't delivered to mauricio.aceiton@unilever.com because the address
couldn't be found, or is unable to receive mail.
"""
    assert extract_failed_recipients_from_ndr(text) == ["mauricio.aceiton@unilever.com"]


def test_gmail_english_was_not_delivered_to():
    text = "Your message was not delivered to farmacia@heel.cl. Learn more"
    assert extract_failed_recipients_from_ndr(text) == ["farmacia@heel.cl"]


def test_gmail_spanish_mensaje_bloqueado_para():
    text = """
** El mensaje se bloqueó **
Se bloqueó tu mensaje para informacion_productos@bestpharma.cl.
Consulta los detalles técnicos que aparecen a continuación.
"""
    assert extract_failed_recipients_from_ndr(text) == ["informacion_productos@bestpharma.cl"]


def test_gmail_spanish_dns_domain_not_found():
    text = """
Tu mensaje no se entregó a ventas@rider.cl porque no encontramos el dominio rider.cl.
La respuesta fue: DNS Error: DNS type 'mx' lookup of rider.cl responded with code NXDOMAIN
"""
    assert extract_failed_recipients_from_ndr(text) == ["ventas@rider.cl"]


def test_gmail_diagnostic_with_final_recipient_still_wins():
    """Final-Recipient remains authoritative when present."""
    text = """
Final-Recipient: rfc822; loreto.castro@bayer.com
Action: failed
Status: 5.1.1
Tu mensaje no se entregó a other@example.com porque no existe.
"""
    assert extract_failed_recipients_from_ndr(text) == ["loreto.castro@bayer.com"]


# --- False-positive guards ---


def test_does_not_extract_bcc_list_from_quoted_original():
    text = """
Tu mensaje no se entregó a failed-only@target.cl porque la dirección no se encuentra.

---------- Original Message ----------
From: contacto@origenlab.cl
To: bcc-one@lab1.cl, bcc-two@lab2.cl, bcc-three@lab3.cl
Cc: bcc-four@lab4.cl
Subject: CYBERDAY OrigenLab — equipos de laboratorio
"""
    assert extract_failed_recipients_from_ndr(text) == ["failed-only@target.cl"]


def test_does_not_extract_campaign_recipients_from_forwarded_block():
    text = """
Your message wasn't delivered to victim@only-victim.cl because the address couldn't be found.

----- Original Message -----
From: OrigenLab <contacto@origenlab.cl>
To: prospect1@a.cl, prospect2@b.cl, prospect3@c.cl, prospect4@d.cl, prospect5@e.cl
"""
    got = extract_failed_recipients_from_ndr(text)
    assert got == ["victim@only-victim.cl"]
    assert "prospect1@a.cl" not in got


def test_does_not_extract_sender_origenlab_from_template():
    text = """
Tu mensaje no se entregó a real-bounce@cliente.cl porque no existe.
De: contacto@origenlab.cl
"""
    assert extract_failed_recipients_from_ndr(text) == ["real-bounce@cliente.cl"]


def test_does_not_extract_domain_only_without_mailbox():
    text = """
Status: 5.4.4
Diagnostic-Code: DNS Error: DNS type 'mx' lookup of example-invalid.cl responded with code NXDOMAIN
Remote server misconfigured
"""
    assert extract_failed_recipients_from_ndr(text) == []


def test_does_not_extract_from_diagnostic_only_without_recipient_evidence():
    text = """
The email account that you tried to reach does not exist.
Please try double-checking the recipient's email address for typos.
"""
    assert extract_failed_recipients_from_ndr(text) == []


def test_multi_final_recipient_dsn_still_allowed():
    """True multi-recipient DSN blocks may list multiple Final-Recipient lines."""
    text = """
Final-Recipient: rfc822; first@client.cl
Final-Recipient: rfc822; second@client.cl
Action: failed
"""
    got = extract_failed_recipients_from_ndr(text)
    assert got == ["first@client.cl", "second@client.cl"]
