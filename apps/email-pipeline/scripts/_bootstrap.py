"""Internal path constants for CLI scripts under ``scripts/``.

This module lives at ``<APP_ROOT>/scripts/_bootstrap.py``. Import it only from other files under
``scripts/`` (after ensuring ``scripts/`` is on ``sys.path`` if needed).

**Preferred execution:** ``cd apps/email-pipeline && uv run python scripts/...`` so the editable
package resolves without relying on ``sys.path`` hacks — see ``scripts/README.md``.
"""

from __future__ import annotations

from pathlib import Path

# ``apps/email-pipeline`` (parent of the ``scripts`` directory).
APP_ROOT: Path = Path(__file__).resolve().parents[1]

# ``apps/email-pipeline/scripts``
SCRIPTS_DIR: Path = Path(__file__).resolve().parent
