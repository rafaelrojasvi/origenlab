from __future__ import annotations

from origenlab_email_pipeline.streamlit_borrador_support import (
    contact_suppression_reason_label,
    fmt_marketing_variant,
)
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import MARKETING_VARIANT_GENERAL


def test_fmt_marketing_variant_known() -> None:
    s = fmt_marketing_variant(MARKETING_VARIANT_GENERAL)
    assert "Presentacion" in s


def test_contact_suppression_reason_label_unknown_returns_raw_or_dash() -> None:
    assert contact_suppression_reason_label("bounce_no_such_user") == "Rebote: no existe la casilla"
    assert contact_suppression_reason_label(None) in ("", "—")
