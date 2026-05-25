"""Validate/normalize cloud Postgres URLs for operator shell scripts (no secrets on stdout)."""

from __future__ import annotations

import re
import shlex
from urllib.parse import urlparse

_PLACEHOLDER_RE = re.compile(
    r"(^|[^a-z0-9_])("
    r"USER:PASSWORD@HOST|user:pass@host|://USER:|://user:pass@|@HOST(?:/|:|$)"
    r")",
    re.IGNORECASE,
)


def ensure_psycopg_driver_url(url: str) -> str:
    """Return URL with SQLAlchemy/psycopg driver prefix (Alembic-compatible)."""
    u = (url or "").strip()
    if not u:
        return u
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if u.startswith(prefix):
            return u
    if u.startswith("postgresql://"):
        return "postgresql+psycopg://" + u[len("postgresql://") :]
    if u.startswith("postgres://"):
        return "postgresql+psycopg://" + u[len("postgres://") :]
    return u


def postgres_url_host_db(url: str) -> str:
    """Safe operator display: ``host[:port]/database`` (never user/password)."""
    parsed = urlparse((url or "").strip())
    host = parsed.hostname or ""
    if not host:
        return "<invalid-host>"
    if parsed.port and parsed.port != 5432:
        host = f"{host}:{parsed.port}"
    db = (parsed.path or "").lstrip("/")
    return f"{host}/{db}" if db else host


def validate_cloud_postgres_url(url: str) -> list[str]:
    """Return human-readable validation errors (empty list = OK)."""
    u = (url or "").strip()
    if not u:
        return ["Postgres URL is empty."]

    if _PLACEHOLDER_RE.search(u):
        return [
            "Postgres URL still contains documentation placeholders "
            "(USER, PASSWORD, HOST, or user:pass@host)."
        ]

    parsed = urlparse(u)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
        "postgres",
    }:
        return [f"Unsupported Postgres URL scheme: {scheme or '(none)'}"]

    if not parsed.hostname:
        return ["Postgres URL has no host."]

    if not (parsed.path or "").strip("/"):
        return ["Postgres URL has no database name."]

    if (parsed.hostname or "").lower() in {"localhost", "127.0.0.1"}:
        return ["Postgres URL host looks local; use Render external URL."]

    return []


def shell_prepare_lines(url: str) -> tuple[int, str]:
    """
    Emit shell ``eval`` lines: NORMALIZED_URL and HOST_DB (quoted).

    On failure returns exit code 2 and error text for stderr only.
    """
    errors = validate_cloud_postgres_url(url)
    if errors:
        msg = "\n".join(f"ERROR: {e}" for e in errors)
        return 2, msg

    normalized = ensure_psycopg_driver_url(url)
    host_db = postgres_url_host_db(url)
    lines = "\n".join(
        (
            f"NORMALIZED_URL={shlex.quote(normalized)}",
            f"HOST_DB={shlex.quote(host_db)}",
        )
    )
    return 0, lines
