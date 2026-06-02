"""Shared stderr deprecation banners for ``scripts/`` entrypoints (stdlib only)."""

from __future__ import annotations

import sys


def print_wrapper_deprecation_warning(root_script: str, canonical_script: str) -> None:
    print(
        f"*** COMPATIBILITY_WRAPPER: {root_script} ***\n"
        f"  Prefer: {canonical_script}\n"
        "  Root path retained for bookmarks; not preferred for new operator commands.",
        file=sys.stderr,
    )
