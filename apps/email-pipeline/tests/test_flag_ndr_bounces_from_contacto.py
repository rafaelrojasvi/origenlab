"""Tests for targeted NDR apply filters in flag_ndr_bounces_from_contacto."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts/tools/flag_ndr_bounces_from_contacto.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("flag_ndr_bounces_from_contacto", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["flag_ndr_bounces_from_contacto"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ndr_tool():
    return _load_script_module()


def test_load_emails_allowlist_skips_comments_and_blanks(tmp_path: Path, ndr_tool) -> None:
    path = tmp_path / "allow.txt"
    path.write_text(
        "# header\n\nfoo@example.com\n  Bar@Example.COM  \n",
        encoding="utf-8",
    )
    assert ndr_tool.load_emails_allowlist(path) == ["foo@example.com", "bar@example.com"]


def test_select_planned_refuses_allowlist_not_in_evidence(ndr_tool) -> None:
    planned = {
        "known@client.cl": ("bounce_no_such_user", "2026-06-01", 1, "Failure"),
        "other@client.cl": ("bounce_other", "2026-06-01", 2, "Failure"),
    }
    selected, refused_missing, refused_wrong = ndr_tool.select_planned_for_apply(
        planned,
        emails_allowlist=["known@client.cl", "ghost@client.cl"],
        only_code="bounce_no_such_user",
    )
    assert selected == {"known@client.cl": planned["known@client.cl"]}
    assert refused_missing == ["ghost@client.cl"]
    assert refused_wrong == []


def test_select_planned_refuses_wrong_code(ndr_tool) -> None:
    planned = {"x@y.cl": ("bounce_other", None, 9, None)}
    selected, refused_missing, refused_wrong = ndr_tool.select_planned_for_apply(
        planned,
        emails_allowlist=["x@y.cl"],
        only_code="bounce_no_such_user",
    )
    assert selected == {}
    assert refused_missing == []
    assert refused_wrong == ["x@y.cl"]


def test_select_planned_only_code_without_file(ndr_tool) -> None:
    planned = {
        "a@x.cl": ("bounce_no_such_user", None, 1, None),
        "b@x.cl": ("bounce_other", None, 2, None),
    }
    selected, refused_missing, refused_wrong = ndr_tool.select_planned_for_apply(
        planned,
        emails_allowlist=None,
        only_code="bounce_no_such_user",
    )
    assert list(selected) == ["a@x.cl"]
    assert refused_missing == []
    assert refused_wrong == []
