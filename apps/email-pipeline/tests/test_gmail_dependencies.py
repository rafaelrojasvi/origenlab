"""Gmail ingest OAuth dependencies (google-auth) must stay declared and importable."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"


def test_pyproject_declares_gmail_group_with_google_auth() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "gmail = [" in text
    assert "google-auth>=" in text
    assert "google-auth-oauthlib>=" in text


def test_gmail_workspace_oauth_google_imports() -> None:
    """Regression: ingest fails at runtime if `uv sync --group gmail` was skipped."""
    pytest.importorskip("google.auth")
    pytest.importorskip("google_auth_oauthlib")
    from google.auth.transport.requests import Request  # noqa: F401
    from google.oauth2.credentials import Credentials  # noqa: F401
    from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401

    from origenlab_email_pipeline import gmail_workspace_oauth

    assert callable(gmail_workspace_oauth.load_credentials_for_gmail_imap)
    assert callable(gmail_workspace_oauth.xoauth2_authenticate)


def test_gmail_ingest_script_imports_oauth_helper_without_running_main() -> None:
    pytest.importorskip("google.auth")
    from origenlab_email_pipeline.gmail_workspace_oauth import (
        load_credentials_for_gmail_imap,
        xoauth2_authenticate,
    )

    assert callable(load_credentials_for_gmail_imap)
    assert callable(xoauth2_authenticate)
