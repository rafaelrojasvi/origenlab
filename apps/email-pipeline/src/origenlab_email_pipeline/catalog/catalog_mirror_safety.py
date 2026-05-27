"""Redaction rules for catalog Postgres mirror (Phase 8C)."""

from __future__ import annotations

import re
from typing import Any

# Legacy bug: alias-style sanitizer removed spaces before lowercase letters/digits.
_BROKEN_PROSE_JOIN_RE = re.compile(r"\s+(?=[a-z\d])")

# Targeted repairs for known legacy joined-word prose only (no generic "de" re-glue).
# Order matters: longer / compound patterns before shorter ones.
_PROSE_JOIN_REPAIRS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"cotizacióny", re.I), "cotización y"),
    (re.compile(r"porcliente", re.I), "por cliente"),
    (re.compile(r"cantidad(\d)", re.I), r"cantidad \1"),
    (re.compile(r"antesdecotizar", re.I), "antes de cotizar"),
    (re.compile(r"\bantesde\b", re.I), "antes de"),
    (re.compile(r"antes decotizar", re.I), "antes de cotizar"),
    (re.compile(r"\bdecotizar\b", re.I), "de cotizar"),
    (re.compile(r"montoes\b", re.I), "monto es"),
    (re.compile(r"Monto(\d)", re.I), r"Monto \1"),
    (re.compile(r"cuerpos decorreo", re.I), "cuerpos de correo"),
    (re.compile(r"cuerposdecorreo", re.I), "cuerpos de correo"),
    (re.compile(r"\bdecorreo\b", re.I), "de correo"),
    (re.compile(r"espejoPostgres", re.I), "espejo Postgres"),
    (re.compile(r"Postgresredactado", re.I), "Postgres redactado"),
    (re.compile(r"siguesiendolafuente", re.I), "sigue siendo la fuente"),
    (re.compile(r"\blafuente\b", re.I), "la fuente"),
    (re.compile(r"Accesoriodecalentamiento", re.I), "Accesorio de calentamiento"),
    (re.compile(r"decalentamiento", re.I), "de calentamiento"),
    (re.compile(r"Tubodevapor", re.I), "Tubo de vapor"),
    (re.compile(r"vaporIKA", re.I), "vapor IKA"),
    (re.compile(r"Catálogooperador", re.I), "Catálogo operador"),
    (re.compile(r"SQLite([a-z])", re.I), r"SQLite \1"),
    (re.compile(r"noincluye", re.I), "no incluye"),
    (re.compile(r"incluyecuerpos", re.I), "incluye cuerpos"),
    (re.compile(r"correonidatos", re.I), "correo ni datos"),
    (re.compile(r"Preciosdeproveedor", re.I), "Precios de proveedor"),
    (re.compile(r"proveedorsondatosinternos", re.I), "proveedor son datos internos"),
    (re.compile(r"nidatosbancarios", re.I), "ni datos bancarios"),
    (re.compile(r"enelectroforesis", re.I), "en electroforesis"),
)

# Substrings that must not appear in operator-facing prose after repair.
FORBIDDEN_JOINED_PROSE_ARTIFACTS: tuple[str, ...] = (
    "cotizacióny",
    "porcliente",
    "cantidad3",
    "antesde",
    "antesdecotizar",
    "decotizar",
    "montoes",
    "Monto112",
    "vaporIKA",
    "decalentamiento",
    "espejoPostgres",
    "lafuente",
    "cuerpos decorreo",
    "oportunida de s",
    "enelectroforesis",
)

# Fields that must keep human-readable Spanish spacing (never alias-collapse).
CATALOG_MIRROR_PROSE_FIELDS: frozenset[str] = frozenset(
    {
        "display_name",
        "brand",
        "manufacturer_name",
        "public_summary",
        "model_number",
        "website_slug",
        "availability_note",
        "price_notes",
        "payment_terms",
        "delivery_terms",
        "spec_value",
        "spec_key",
        "supplier_org_name",
        "link_ref",
        "deal_label",
        "source_summary",
        "client_org_name",
    }
)

FORBIDDEN_MIRROR_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bbank\b",
        r"\bbanco\b",
        r"\bswift\b",
        r"\biban\b",
        r"\bcuenta\b",
        r"\bbeneficiario\b",
        r"\brut\b",
        r"gmail\.com",
        r"mail\.google",
        r"source_file",
        r"transfer_id",
        r"operation_id",
    )
)

FORBIDDEN_MIRROR_KEYS: frozenset[str] = frozenset(
    {
        "evidence_email_id",
        "evidence_attachment_id",
        "notes",
        "transfer_id",
        "operation_id",
        "source_file",
        "source_preview_path",
        "gmail_url",
        "body",
        "full_text",
        "email_body",
    }
)


class CatalogMirrorSafetyError(ValueError):
    """Raised when mirror payload contains forbidden content."""


def repair_catalog_prose_spacing(value: str) -> str:
    """Fix legacy joined-word spacing; leave already-correct prose unchanged."""
    out = value
    for pattern, replacement in _PROSE_JOIN_REPAIRS:
        out = pattern.sub(replacement, out)
    return out


def assert_catalog_prose_spacing(value: str | None, *, field: str) -> None:
    """Reject known joined-word artifacts in operator-facing Spanish prose."""
    if value is None or value == "":
        return
    lowered = value.lower()
    for artifact in FORBIDDEN_JOINED_PROSE_ARTIFACTS:
        if artifact.lower() in lowered:
            raise CatalogMirrorSafetyError(
                f"joined-word spacing in {field}: contains {artifact!r}"
            )


def prepare_catalog_mirror_text(value: str | None, *, field: str) -> str | None:
    """Repair legacy spacing, then enforce mirror safety (read/API path)."""
    if value is None or value == "":
        return value
    cleaned = repair_catalog_prose_spacing(value)
    assert_mirror_text_safe(cleaned, field=field)
    assert_catalog_prose_spacing(cleaned, field=field)
    return cleaned


def validate_catalog_prose_field(value: object, *, field: str) -> object:
    """Pydantic before-validator: repair prose fields on API model construction."""
    if value is None or not isinstance(value, str):
        return value
    return prepare_catalog_mirror_text(value, field=field)


def assert_mirror_text_safe(value: str | None, *, field: str) -> None:
    if value is None or value == "":
        return
    for pat in FORBIDDEN_MIRROR_TEXT_PATTERNS:
        if pat.search(value):
            raise CatalogMirrorSafetyError(
                f"forbidden content in {field}: matched {pat.pattern!r}"
            )


def assert_mirror_row_safe(row: dict[str, Any], *, table: str) -> None:
    for key in row:
        if key in FORBIDDEN_MIRROR_KEYS:
            raise CatalogMirrorSafetyError(f"{table}: forbidden key {key!r}")
    for key, value in row.items():
        if isinstance(value, str):
            field = f"{table}.{key}"
            if key in CATALOG_MIRROR_PROSE_FIELDS:
                row[key] = prepare_catalog_mirror_text(value, field=field)
            else:
                assert_mirror_text_safe(value, field=field)
