"""Contract: pipeline UTC timestamp string format stays stable."""

from __future__ import annotations

import re

from origenlab_email_pipeline.timeutil import now_iso


def test_now_iso_matches_utc_z_pattern() -> None:
    s = now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s) is not None
