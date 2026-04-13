"""JSON serialization for client report artifacts (summary.json, etc.)."""

from __future__ import annotations

import json

try:
    import orjson
except ImportError:
    orjson = None  # type: ignore


def dumps_report_json(obj: object) -> bytes:
    """Pretty JSON as UTF-8 bytes; uses ``orjson`` when installed (same as prior script)."""
    if orjson:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return json.dumps(obj, indent=2, ensure_ascii=False).encode()
