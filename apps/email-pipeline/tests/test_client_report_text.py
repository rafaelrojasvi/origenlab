"""Tests for client report MIME/text helpers."""

from __future__ import annotations

import base64

import pytest

from origenlab_email_pipeline.client_report_text import (
    decode_mime_header_value,
    is_bounce_sender_for_report,
)


def test_decode_mime_header_value_none_and_plain() -> None:
    assert decode_mime_header_value(None) == ""
    assert decode_mime_header_value("  plain subject  ") == "plain subject"


def test_decode_mime_header_value_rfc2047_q_encoded() -> None:
    # UTF-8 "Café" as Q-encoded word
    raw = "=?UTF-8?Q?Caf=C3=A9?="
    out = decode_mime_header_value(raw)
    assert out == "Café"


def test_decode_mime_header_value_rfc2047_b_encoded() -> None:
    raw = "=?utf-8?b?" + base64.b64encode("héllo".encode("utf-8")).decode("ascii") + "?="
    assert decode_mime_header_value(raw) == "héllo"


def test_decode_mime_header_value_falls_back_on_decode_header_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import origenlab_email_pipeline.client_report_text as crt

    def _boom(_s: str):
        raise RuntimeError("decode failed")

    monkeypatch.setattr(crt, "decode_header", _boom)
    s = "=?utf-8?q?xx?="
    assert decode_mime_header_value(s) == s.strip()


@pytest.mark.parametrize(
    "sender,expected",
    [
        ("MAILER-DAEMON@x.com", True),
        ("Mail Delivery Subsystem <noreply>", True),
        ("postmaster@corp.net", True),
        ("x <postmaster@y.org>", True),
        ("Lab <compras@cliente.cl>", False),
        ("", False),
    ],
)
def test_is_bounce_sender_for_report(sender: str, expected: bool) -> None:
    assert is_bounce_sender_for_report(sender) is expected
