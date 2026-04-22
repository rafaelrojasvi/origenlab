"""Stable core import surface for configuration helpers.

Implementation currently lives in :mod:`origenlab_email_pipeline.config`.
This module re-exports that public API. Do not move runtime logic here yet;
this file exists so new code can ``from origenlab_email_pipeline.core import config``
(``core`` package) or ``from origenlab_email_pipeline.core import config as config``
without a physical file move of :mod:`origenlab_email_pipeline.config`.
"""

from __future__ import annotations

from ..config import *  # noqa: F401,F403
