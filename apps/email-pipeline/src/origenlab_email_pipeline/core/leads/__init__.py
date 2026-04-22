"""Stable **leads** import surface (re-exports only; Stage 2B).

Sibling modules in this package (e.g. :mod:`origenlab_email_pipeline.core.leads.leads_schema`)
re-export the corresponding top-level library modules under :mod:`origenlab_email_pipeline`
(``leads_schema``, ``lead_contact_research``, …).

**No implementation is moved here yet.** Existing ``from origenlab_email_pipeline.leads_schema import …``
imports remain valid.

This ``__init__`` does **not** auto-import submodules — import the specific submodule you need
(``from origenlab_email_pipeline.core.leads import leads_schema``) to avoid eager loading and
side effects.
"""

from __future__ import annotations

__all__: list[str] = []
