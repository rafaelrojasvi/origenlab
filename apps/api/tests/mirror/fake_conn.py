"""Mock Postgres connection for mirror dashboard summary tests."""

from __future__ import annotations

from typing import Any

SCRATCH_CANONICAL = {
    "mart.contact_master_canonical": 497,
    "mart.organization_master_canonical": 261,
    "mart.opportunity_signals_canonical": 200,
}
SCRATCH_ARCHIVE = {
    "mart.contact_master": 27198,
    "mart.organization_master": 10688,
    "mart.opportunity_signals": 2705,
}


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class SummaryFakeConn:
    """Minimal psycopg-like connection for dashboard summary mirror tests."""

    def __init__(self) -> None:
        self.tables = {
            ("mart", "contact_master"): True,
            ("mart", "organization_master"): True,
            ("mart", "opportunity_signals"): True,
            ("mart", "contact_master_canonical"): True,
            ("mart", "organization_master_canonical"): True,
            ("mart", "opportunity_signals_canonical"): True,
            ("outbound", "contact_email_suppression"): True,
            ("outbound", "contact_domain_suppression"): True,
            ("outbound", "outreach_contact_state"): True,
        }
        self.counts = {**SCRATCH_ARCHIVE, **SCRATCH_CANONICAL}
        self.counts.update(
            {
                "outbound.contact_email_suppression": 2,
                "outbound.contact_domain_suppression": 1,
                "outbound.outreach_contact_state": 4,
            }
        )

    def _count_cursor(self, qualified: str) -> _FakeCursor:
        return _FakeCursor([{"n": self.counts[qualified]}])

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "information_schema.tables" in s:
            schema = params[0]
            table = params[1]
            ok = self.tables.get((schema, table), False)
            return _FakeCursor([{"?": 1}] if ok else [])
        if "count(*)" in s:
            for qualified in (
                "mart.contact_master_canonical",
                "mart.organization_master_canonical",
                "mart.opportunity_signals_canonical",
                "mart.contact_master",
                "mart.organization_master",
                "mart.opportunity_signals",
            ):
                if qualified in s:
                    return self._count_cursor(qualified)
        if "count(*)" in s and "contact_email_suppression" in s:
            return _FakeCursor([{"n": self.counts["outbound.contact_email_suppression"]}])
        if "count(*)" in s and "contact_domain_suppression" in s:
            return _FakeCursor([{"n": self.counts["outbound.contact_domain_suppression"]}])
        if "from outbound.contact_email_suppression" in s and "select email" in s:
            return _FakeCursor(
                [
                    {
                        "email": "bad@example.cl",
                        "suppression_reason_code": "manual",
                        "suppression_reason_text": None,
                        "suppression_source": None,
                        "last_bounced_at": None,
                        "updated_at": None,
                        "updated_by": None,
                    }
                ]
            )
        if "from outbound.outreach_contact_state" in s and "select contact_email_norm" in s:
            return _FakeCursor(
                [
                    {
                        "contact_email_norm": "lead@example.cl",
                        "state": "contacted",
                        "first_contacted_at": None,
                        "last_contacted_at": None,
                        "source": "manual",
                        "notes": None,
                        "updated_at": None,
                        "updated_by": None,
                        "lead_id": 1,
                    }
                ]
            )
        if "count(*)" in s and "outreach_contact_state" in s:
            if "group by" in s:
                return _FakeCursor([{"st": "contacted", "n": 2}])
            return _FakeCursor([{"n": self.counts["outbound.outreach_contact_state"]}])
        if "count(*)" in s and "contact_email_suppression" in s and "group by" not in s:
            return _FakeCursor([{"n": self.counts["outbound.contact_email_suppression"]}])
        if "max(last_seen_at)" in s and "contact_master" in s:
            return _FakeCursor([{"m": None}])
        if "max(last_seen_at)" in s and "organization_master" in s:
            return _FakeCursor([{"m": None}])
        if "max(created_at)" in s and "opportunity_signals" in s:
            return _FakeCursor([{"m": None}])
        if "select 1" in s:
            return _FakeCursor([{"?": 1}])
        return _FakeCursor([{"n": 0}])


# Alias for readiness + dashboard mirror tests.
MirrorFakeConn = SummaryFakeConn
