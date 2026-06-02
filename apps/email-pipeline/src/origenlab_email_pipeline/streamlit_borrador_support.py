"""Deprecated compatibility shim — import from ``tatiana_copilot.borrador_support`` (Streamlit retirement S2)."""

from __future__ import annotations

from origenlab_email_pipeline.tatiana_copilot.borrador_support import (
    contact_suppression_reason_label,
    fmt_marketing_variant,
    load_existing_pilot_batch,
    pilot_batch_signature,
)

__all__ = [
    "contact_suppression_reason_label",
    "fmt_marketing_variant",
    "load_existing_pilot_batch",
    "pilot_batch_signature",
]
