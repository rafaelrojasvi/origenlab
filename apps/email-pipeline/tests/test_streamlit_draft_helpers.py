from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.config import Settings
from origenlab_email_pipeline.tatiana_copilot.generator import MockDraftGenerator
from origenlab_email_pipeline.tatiana_copilot.streamlit_draft_helpers import (
    draft_case_from_email_row,
    draft_case_from_manual,
    resolve_streamlit_generator,
)


def test_resolve_streamlit_generator_mock_explicit() -> None:
    s = Settings()
    gen, name = resolve_streamlit_generator(
        generator_name="openai_chat",
        use_mock_explicit=True,
        settings=s,
    )
    assert name == "mock"
    assert isinstance(gen, MockDraftGenerator)


def test_resolve_streamlit_generator_rejects_mock_without_explicit_flag() -> None:
    s = Settings()
    with pytest.raises(ValueError, match="Simulación|simulación|OpenAI"):
        resolve_streamlit_generator(
            generator_name="mock",
            use_mock_explicit=False,
            settings=s,
        )


def test_draft_case_from_manual_metadata() -> None:
    c = draft_case_from_manual(
        case_id="t1",
        subject="S",
        body_text="Hola",
        requester_name="Ana",
    )
    assert c.case_id == "t1"
    assert c.context_metadata.get("requester_name") == "Ana"
    assert c.context_metadata.get("intake") == "streamlit_manual"


def test_draft_case_from_email_row(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          subject TEXT,
          sender TEXT,
          source_file TEXT,
          date_iso TEXT,
          top_reply_clean TEXT,
          full_body_clean TEXT,
          body_text_clean TEXT,
          body TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO emails (id, subject, sender, source_file, date_iso, top_reply_clean) VALUES (1, 'Sub', 'a@b', 'x', '2026-01-01', 'Cuerpo limpio')",
    )
    conn.commit()
    case = draft_case_from_email_row(conn, email_id=1)
    conn.close()
    assert case is not None
    assert case.case_id == "gmail_contacto_1"
    assert case.body_text == "Cuerpo limpio"
