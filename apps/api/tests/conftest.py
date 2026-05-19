"""Prefer apps/api ``origenlab_api`` over email-pipeline mirror package name."""

from __future__ import annotations

import sys
from pathlib import Path

_API_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))
