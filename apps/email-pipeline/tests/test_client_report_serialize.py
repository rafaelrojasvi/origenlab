"""Tests for client report JSON serialization."""

from __future__ import annotations

import json

from origenlab_email_pipeline.client_report_serialize import dumps_report_json


def test_dumps_report_json_roundtrip_unicode() -> None:
    obj = {"x": 1, "nested": {"label": "café"}}
    raw = dumps_report_json(obj)
    assert isinstance(raw, bytes)
    assert json.loads(raw.decode("utf-8")) == obj


def test_dumps_report_json_is_indented_utf8() -> None:
    raw = dumps_report_json({"a": 1, "b": 2})
    text = raw.decode("utf-8")
    assert "\n" in text
    assert '"a"' in text and '"b"' in text
