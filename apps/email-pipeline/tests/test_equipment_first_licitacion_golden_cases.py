"""Golden regression cases for equipment-first ChileCompra tender matching.

These tests intentionally cover business-quality behavior rather than HTTP/API wiring:
which tender text should become an operator queue row, which should be ignored,
and which next_action/category should be preserved as rules evolve.
"""

from __future__ import annotations
