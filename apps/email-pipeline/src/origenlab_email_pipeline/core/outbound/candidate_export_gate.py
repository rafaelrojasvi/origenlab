"""Stable core outbound import surface for export gate policy.

Implementation currently lives in :mod:`origenlab_email_pipeline.candidate_export_gate`.
This wrapper exists so future code can import from :mod:`origenlab_email_pipeline.core.outbound`
without moving tested logic yet.
"""

from __future__ import annotations

from ...candidate_export_gate import *  # noqa: F401,F403
