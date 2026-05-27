"""Tests for catalog mirror prose spacing and redaction safety."""

from __future__ import annotations

import re

import pytest

from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    CatalogMirrorSafetyError,
    assert_catalog_prose_spacing,
    prepare_catalog_mirror_text,
    repair_catalog_prose_spacing,
)

# Legacy alias-style bug that must never be applied to prose fields.
_LEGACY_BROKEN_PROSE_SANITIZER = re.compile(r"\s+(?=[a-z\d])")


def _legacy_broken_prose_sanitizer(text: str) -> str:
    return _LEGACY_BROKEN_PROSE_SANITIZER.sub("", text)


def test_legacy_broken_sanitizer_produces_joined_words() -> None:
    raw = (
        "cotización y disponibilidad; solicitado por cliente, cantidad 3; "
        "monto es precio; Monto 112,00; antes de cotizar."
    )
    broken = _legacy_broken_prose_sanitizer(raw)
    assert "cotizacióny" in broken
    assert "porcliente" in broken
    assert "cantidad3" in broken
    assert "montoes" in broken
    assert "Monto112" in broken
    assert "antesde" in broken


def test_repair_catalog_prose_spacing_fixes_legacy_joins() -> None:
    broken = (
        "cotizacióny disponibilidad; solicitado porcliente, cantidad3; "
        "montoes precio; Monto112,00; antesde cotizar."
    )
    fixed = repair_catalog_prose_spacing(broken)
    assert "cotización y disponibilidad" in fixed
    assert "por cliente" in fixed
    assert "cantidad 3" in fixed
    assert "monto es" in fixed
    assert "Monto 112,00" in fixed
    assert "antes de cotizar" in fixed


def test_prepare_catalog_mirror_text_preserves_good_spanish() -> None:
    good = "Tubo de vapor IKA RV10.70 solicitado por cliente (RG Energía), cantidad 3."
    assert prepare_catalog_mirror_text(good, field="test") == good


def test_assert_catalog_prose_spacing_rejects_joined_words() -> None:
    with pytest.raises(CatalogMirrorSafetyError, match="joined-word"):
        assert_catalog_prose_spacing("cotizacióny disponibilidad", field="test")
