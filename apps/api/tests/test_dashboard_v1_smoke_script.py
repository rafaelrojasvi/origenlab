"""Dashboard v1 HTTP smoke script — route list and sqlite validation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = API_ROOT / "scripts" / "dashboard_v1_http_smoke.py"


def test_dashboard_v1_smoke_script_sqlite_ok() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--expect-backend", "sqlite"],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "GET /health" in proc.stdout
    assert '"ok": true' in proc.stdout or '"ok":true' in proc.stdout.replace(" ", "")


def test_smoke_script_does_not_include_legacy_paths() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    route_section = text.split("DASHBOARD_V1_ROUTES")[1].split("FORBIDDEN_LEGACY_PREFIXES")[0]
    assert '"/dashboard' not in route_section
    assert '"/classification' not in route_section
    assert "FORBIDDEN_LEGACY_PREFIXES" in text
