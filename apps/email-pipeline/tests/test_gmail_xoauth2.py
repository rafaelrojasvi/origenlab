from __future__ import annotations

from origenlab_email_pipeline.gmail_workspace_oauth import xoauth2_initial_response


def test_xoauth2_initial_response_shape() -> None:
    blob = xoauth2_initial_response("contacto@origenlab.cl", "fake-access-token")
    decoded = blob.decode("utf-8")
    assert decoded.startswith("user=contacto@origenlab.cl\x01auth=Bearer ")
    assert decoded.endswith("\x01\x01")
