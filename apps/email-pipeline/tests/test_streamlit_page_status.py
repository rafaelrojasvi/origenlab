from __future__ import annotations

from unittest.mock import MagicMock

import origenlab_email_pipeline.streamlit_page_status as page_status_mod
from origenlab_email_pipeline.streamlit_page_status import (
    PAGE_STATUS_PRESETS,
    page_status_values,
)


def test_page_status_presets_include_prioridad_pages() -> None:
    for key in (
        "Qué hacer hoy",
        "Casos para revisar",
        "Cola outreach marketing",
        "Borrador comercial",
    ):
        assert key in PAGE_STATUS_PRESETS
        v = page_status_values(key)
        assert "source" in v and "freshness" in v
        assert v["source"]
        assert v["freshness"]


def test_que_hacer_hoy_copy_mentions_multi_source() -> None:
    src = page_status_values("Qué hacer hoy")["source"]
    assert "Varias tablas" in src or "varias" in src.lower()


def test_render_page_status_includes_action_hint_and_note(monkeypatch) -> None:
    seq: list[tuple[str, str]] = []

    class _Col:
        def __enter__(self) -> _Col:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(page_status_mod.st, "markdown", lambda x: seq.append(("md", str(x))))
    monkeypatch.setattr(page_status_mod.st, "caption", lambda x: seq.append(("cap", str(x))))
    monkeypatch.setattr(page_status_mod.st, "columns", MagicMock(return_value=(_Col(), _Col())))

    page_status_mod.render_page_status("Casos para revisar", action_hint="HINT_LINE", note="NOTE_LINE")

    caps = [t for kind, t in seq if kind == "cap"]
    mds = [t for kind, t in seq if kind == "md"]
    assert any("Próximo paso sugerido" in c for c in caps)
    assert any("HINT_LINE" in m for m in mds)
    assert any("NOTE_LINE" in c for c in caps)
