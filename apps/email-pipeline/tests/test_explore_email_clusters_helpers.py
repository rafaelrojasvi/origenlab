from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_explore_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "scripts" / "ml" / "explore_email_clusters.py"
    spec = importlib.util.spec_from_file_location("explore_email_clusters", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def test_voice_sender_domain_sql_or_builds_like_clauses() -> None:
    m = _load_explore_module()
    sql, params = m.voice_sender_domain_sql_or(frozenset({"labdelivery.cl"}))
    assert "LOWER(COALESCE(sender,''))" in sql
    assert "%@labdelivery.cl" in params
    assert "%.labdelivery.cl" in params
    assert sql.count("LIKE ?") == 3


def test_voice_sender_domain_sql_or_empty_domains() -> None:
    m = _load_explore_module()
    sql, params = m.voice_sender_domain_sql_or(frozenset())
    assert sql == "1=0"
    assert params == []


def test_voice_phish_body_substrings_defined() -> None:
    m = _load_explore_module()
    assert len(m._VOICE_PHISH_BODY_SUBSTRINGS) >= 5
    assert len(m._VOICE_PHISH_SUBJECT_SUBSTRINGS) >= 5
