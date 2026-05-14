"""Internal-domain inference excludes ESP/relay/hosting noise."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.business_mart import (
    infer_internal_domains_from_top_senders,
    is_infrastructure_domain_guess,
)


@pytest.mark.parametrize(
    ("domain", "expect_infra"),
    [
        ("mailchannels.net", True),
        ("bounce.mailchannels.net", True),
        ("rs2.websitehostserver.net", True),
        ("track.mailchannels.net", True),
        ("origenlab.cl", False),
        ("labdelivery.cl", False),
        ("contacto.origenlab.cl", False),
    ],
)
def test_is_infrastructure_domain_guess(domain: str, expect_infra: bool) -> None:
    assert is_infrastructure_domain_guess(domain) is expect_infra


def test_infer_internal_domains_skips_mailchannels_and_hosting() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE emails (sender TEXT)")
    for _ in range(25):
        conn.execute("INSERT INTO emails VALUES (?)", ("N <n@bounce.mailchannels.net>",))
    for _ in range(20):
        conn.execute("INSERT INTO emails VALUES (?)", ("H <h@rs2.websitehostserver.net>",))
    for _ in range(5):
        conn.execute("INSERT INTO emails VALUES (?)", ("A <a@origenlab.cl>",))
    conn.commit()
    got = infer_internal_domains_from_top_senders(conn, max_n=3, sender_limit=50)
    assert "origenlab.cl" in got
    assert "mailchannels.net" not in got
    assert "websitehostserver.net" not in got
