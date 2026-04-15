"""Compatibility shim — implementation moved to ``commercial.commercial_intel_schema``.

**Deprecated import path:** ``origenlab_email_pipeline.commercial_intel_schema`` remains
supported for stable call sites; new code may use
``origenlab_email_pipeline.commercial.commercial_intel_schema`` instead.
"""

from __future__ import annotations

from origenlab_email_pipeline.commercial.commercial_intel_schema import *  # noqa: F403
