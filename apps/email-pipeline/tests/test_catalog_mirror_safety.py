"""Tests for catalog mirror prose spacing and redaction safety."""

from __future__ import annotations

import re

import pytest

from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    FORBIDDEN_JOINED_PROSE_ARTIFACTS,
    CatalogMirrorSafetyError,
    assert_catalog_prose_spacing,
    prepare_catalog_mirror_text,
    repair_catalog_prose_spacing,
)

# Legacy alias-style bug that must never be applied to prose fields.
_LEGACY_BROKEN_PROSE_SANITIZER = re.compile(r"\s+(?=[a-z\d])")


def _legacy_broken_prose_sanitizer(text: str) -> str:
    return _LEGACY_BROKEN_PROSE_SANITIZER.sub("", text)


@pytest.mark.parametrize(
    ("broken", "fixed_phrase"),
    [
        ("cotizacióny disponibilidad", "cotización y disponibilidad"),
        ("solicitado porcliente", "por cliente"),
        ("cantidad3", "cantidad 3"),
        ("antesde cotizar", "antes de cotizar"),
        ("antes decotizar", "antes de cotizar"),
        ("montoes", "monto es"),
        ("Monto112,00", "Monto 112,00"),
        ("confirmar antesdecotizar al cliente", "antes de cotizar"),
        ("Tubo de vaporIKA RV10.70", "vapor IKA"),
        ("Accesorio decalentamiento", "de calentamiento"),
        ("espejoPostgres redactado", "espejo Postgres"),
        ("siendo lafuente operativa", "la fuente"),
        ("cuerpos decorreo ni datos", "cuerpos de correo"),
    ],
)
def test_repair_catalog_prose_spacing_live_phrases(broken: str, fixed_phrase: str) -> None:
    assert fixed_phrase in repair_catalog_prose_spacing(broken)


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


def test_repair_catalog_prose_spacing_fixes_legacy_join_bundle() -> None:
    broken = (
        "cotizacióny disponibilidad; solicitado porcliente, cantidad3; "
        "montoes precio; Monto112,00; antesde cotizar; confirmar antes decotizar."
    )
    fixed = repair_catalog_prose_spacing(broken)
    for artifact in FORBIDDEN_JOINED_PROSE_ARTIFACTS:
        assert artifact.lower() not in fixed.lower()


def test_prepare_catalog_mirror_text_preserves_good_spanish() -> None:
    good = "Tubo de vapor IKA RV10.70 solicitado por cliente (RG Energía), cantidad 3."
    assert prepare_catalog_mirror_text(good, field="test") == good


@pytest.mark.parametrize(
    "word",
    [
        "oportunidades",
        "modelo",
        "disponibilidad",
        "proveedor",
        "cotización",
        "categoría",
    ],
)
def test_repair_does_not_break_common_spanish_words(word: str) -> None:
    sample = f"Texto con {word} para el catálogo operador."
    assert repair_catalog_prose_spacing(sample) == sample
    assert prepare_catalog_mirror_text(sample, field="test") == sample


def test_prepare_catalog_disclaimer_repairs_legacy_joined_constant() -> None:
    from origenlab_email_pipeline.postgres_dashboard_api.schemas import CATALOG_DISCLAIMER

    broken = _legacy_broken_prose_sanitizer(CATALOG_DISCLAIMER)
    assert "Postgresredactado" in broken
    assert "lafuente" in broken
    assert "cuerposdecorreo" in broken
    fixed = prepare_catalog_mirror_text(broken, field="response.disclaimer")
    assert fixed is not None
    assert "espejo Postgres" in fixed
    assert "la fuente" in fixed
    assert "cuerpos de correo" in fixed


def test_assert_catalog_prose_spacing_rejects_joined_words() -> None:
    with pytest.raises(CatalogMirrorSafetyError, match="joined-word"):
        assert_catalog_prose_spacing("cotizacióny disponibilidad", field="test")
