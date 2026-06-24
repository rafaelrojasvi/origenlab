"""
Tests for body extraction (Phase 2.1): plain/html/mixed, cleaning, source type.
"""
from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from origenlab_email_pipeline.parse_mbox import (
    body_content,
    decode_payload,
    extract_body_structured,
    html_to_text,
    html_to_text_improved,
)


# --- Helpers to build messages ---


def _make_plain_message(body: str, charset: str = "utf-8") -> MIMEText:
    msg = MIMEText(body, "plain", _charset=charset)
    msg["Subject"] = "Test"
    return msg


def _make_html_message(html: str, charset: str = "utf-8") -> MIMEText:
    msg = MIMEText(html, "html", _charset=charset)
    msg["Subject"] = "Test"
    return msg


def _make_multipart_plain_html(plain: str, html: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Test"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


# --- body_content backward compatibility ---


def test_body_content_plain_only():
    """Plain-only email: body is the plain text, body_html empty."""
    msg = _make_plain_message("Hello world.\n\nThis is plain.")
    body, body_html = body_content(msg)
    assert body == "Hello world.\n\nThis is plain."
    assert body_html == ""


def test_body_content_html_only():
    """HTML-only email: body is HTML stripped to text, body_html has raw HTML."""
    msg = _make_html_message("<p>Hello</p><p>World</p>")
    body, body_html = body_content(msg)
    assert "Hello" in body and "World" in body
    assert "<p>" in body_html


def test_body_content_multipart_prefers_plain():
    """Multipart with both: body_content prefers plain."""
    msg = _make_multipart_plain_html("Plain part", "<p>HTML part</p>")
    body, body_html = body_content(msg)
    assert body.strip() == "Plain part"
    assert "HTML" in body_html


# --- extract_body_structured ---


def test_extract_plain_only():
    """Plain-only: source_type plain, has_plain True, has_html False."""
    msg = _make_plain_message("Only plain text here.")
    out = extract_body_structured(msg)
    assert out["body_source_type"] == "plain"
    assert out["body_has_plain"] is True
    assert out["body_has_html"] is False
    assert out["body_text_raw"] == "Only plain text here."
    assert out["body_text_clean"] == "Only plain text here."


def test_extract_html_only():
    """HTML-only: source_type html, clean uses improved stripping."""
    msg = _make_html_message("<p>Hello</p><p>World</p>")
    out = extract_body_structured(msg)
    assert out["body_source_type"] == "html"
    assert out["body_has_plain"] is False
    assert out["body_has_html"] is True
    assert "Hello" in out["body_text_clean"] and "World" in out["body_text_clean"]


def test_extract_multipart_both():
    """Multipart with both plain and html: source_type mixed, prefer plain."""
    msg = _make_multipart_plain_html("Plain content", "<p>HTML content</p>")
    out = extract_body_structured(msg)
    assert out["body_source_type"] == "mixed"
    assert out["body_has_plain"] is True
    assert out["body_has_html"] is True
    assert out["body_text_raw"] == "Plain content"
    assert out["body_text_clean"] == "Plain content"


def test_extract_empty_or_attachment_only():
    """Message with no text/plain and no text/html: empty."""
    msg = MIMEMultipart()
    msg["Subject"] = "No body"
    # No text parts attached
    out = extract_body_structured(msg)
    assert out["body_source_type"] == "empty"
    assert out["body_has_plain"] is False
    assert out["body_has_html"] is False
    assert out["body_text_raw"] == ""
    assert out["body_text_clean"] == ""


def test_extract_html_with_scripts_and_styles():
    """HTML with script/style: improved cleaner removes them."""
    html = "<script>alert(1)</script><style>.x{}</style><p>Visible</p>"
    msg = _make_html_message(html)
    out = extract_body_structured(msg)
    assert out["body_source_type"] == "html"
    assert "Visible" in out["body_text_clean"]
    assert "alert" not in out["body_text_clean"]
    assert ".x" not in out["body_text_clean"]


def test_extract_broken_charset_decoding():
    """Broken or unknown charset: decode_payload falls back to utf-8 replace."""
    # Latin-1 bytes that are invalid in UTF-8 could be decoded as replacement char
    msg = _make_plain_message("Normal ascii")
    out = extract_body_structured(msg)
    assert out["body_text_clean"] == "Normal ascii"
    # Explicit decode test
    result = decode_payload(b"hello \xff world", "utf-8")
    assert "hello" in result and "world" in result


def test_html_to_text_removes_script_and_style() -> None:
    html = "<script>alert(1)</script><style>.x{}</style><p>Visible</p>"
    assert "Visible" in html_to_text(html)
    assert "alert" not in html_to_text(html)
    assert ".x" not in html_to_text(html)


def test_html_to_text_unescapes_entities() -> None:
    assert html_to_text("<p>Tom &amp; Jerry &lt;3</p>") == "Tom & Jerry <3"


def test_html_to_text_improved_preserves_block_spacing() -> None:
    html = "<p>Line one</p><div>Line two</div><br><li>Item</li>"
    text = html_to_text_improved(html)
    assert "Line one" in text
    assert "Line two" in text
    assert "Item" in text
    assert "\n" in text


def test_html_to_text_handles_malformed_html_without_crashing() -> None:
    malformed = "<p>Hello<script>bad<<div>World</p>"
    assert "Hello" in html_to_text(malformed)
    assert html_to_text_improved(malformed)