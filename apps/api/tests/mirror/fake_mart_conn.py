"""Mock Postgres connection for mirror mart contact/organization list tests."""

from __future__ import annotations

from typing import Any

from fake_conn import SCRATCH_ARCHIVE, SCRATCH_CANONICAL, SummaryFakeConn, _FakeCursor


class MartListsFakeConn(SummaryFakeConn):
    """SummaryFakeConn plus mart list row fixtures (slice1 parity)."""

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from mart.contact_master_canonical" in s and "select email" in s:
            return _FakeCursor(
                [
                    {
                        "email": "lab@example.cl",
                        "contact_name_best": "Lab",
                        "domain": "example.cl",
                        "organization_name_guess": "Example",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 1,
                        "confidence_score": 0.9,
                        "top_equipment_tags": "micro",
                    }
                ]
            )
        if "from mart.organization_master_canonical" in s and "select domain" in s:
            return _FakeCursor(
                [
                    {
                        "domain": "lab.cl",
                        "organization_name_guess": "Lab Canonical",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 10,
                        "total_contacts": 2,
                        "top_equipment_tags": None,
                        "key_contacts": None,
                    }
                ]
            )
        if "from mart.organization_master" in s and "select domain" in s:
            if "organization_master_canonical" in s:
                return super().execute(sql, params)
            return _FakeCursor(
                [
                    {
                        "domain": "archive.cl",
                        "organization_name_guess": "Archive Org",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 100,
                        "total_contacts": 20,
                        "top_equipment_tags": None,
                        "key_contacts": None,
                    }
                ]
            )
        if "from mart.contact_master" in s and "select email" in s:
            if "contact_master_canonical" in s:
                return super().execute(sql, params)
            return _FakeCursor(
                [
                    {
                        "email": "archive@example.cl",
                        "contact_name_best": "Lab",
                        "domain": "example.cl",
                        "organization_name_guess": "Example",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 1,
                        "confidence_score": 0.9,
                        "top_equipment_tags": "micro",
                    }
                ]
            )
        return super().execute(sql, params)
