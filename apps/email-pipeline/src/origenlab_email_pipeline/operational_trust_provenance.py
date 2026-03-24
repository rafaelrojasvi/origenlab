"""Client pack freshness and audit-markdown DB path checks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from origenlab_email_pipeline.operational_trust_csv import load_client_pack_summary, parse_iso_utc
from origenlab_email_pipeline.operational_trust_types import AUDIT_DB_LINE_RE, TrustCheck


def check_stale_client_pack(
    summary_path: Path,
    *,
    max_age_hours: float,
) -> TrustCheck:
    summary = load_client_pack_summary(summary_path)
    if not summary:
        return TrustCheck(
            "client_pack_summary_exists",
            ok=False,
            critical=True,
            message=f"Missing or invalid summary: {summary_path}",
        )
    gen = summary.get("generated_at_utc") or ""
    dt = parse_iso_utc(str(gen))
    if dt is None:
        return TrustCheck(
            "client_pack_generated_at_parse",
            ok=False,
            critical=True,
            message=f"Cannot parse generated_at_utc: {gen!r}",
        )
    age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    ok = age_h <= max_age_hours
    return TrustCheck(
        "client_pack_freshness",
        ok=ok,
        critical=True,
        message=(
            f"client_pack generated_at_utc is within {max_age_hours}h "
            f"(age {age_h:.1f}h)"
            if ok
            else f"Stale client_pack: generated {age_h:.1f}h ago (limit {max_age_hours}h)"
        ),
        details={"generated_at_utc": gen, "age_hours": age_h},
    )


def check_provenance_db_path(
    *,
    resolved_db: Path,
    audit_md_path: Path,
) -> TrustCheck:
    if not audit_md_path.is_file():
        return TrustCheck(
            "provenance_audit_exists",
            ok=False,
            critical=False,
            message=f"No CONTACT_READINESS_AUDIT.md at {audit_md_path} (skip path compare)",
        )
    text = audit_md_path.read_text(encoding="utf-8")
    m = AUDIT_DB_LINE_RE.search(text)
    if not m:
        return TrustCheck(
            "provenance_audit_db_line",
            ok=False,
            critical=False,
            message="Could not find **Base de datos usada:** line in audit markdown",
        )
    recorded = Path(m.group(1).strip()).resolve()
    actual = resolved_db.resolve()
    ok = recorded == actual
    return TrustCheck(
        "provenance_audit_db_matches_config",
        ok=ok,
        critical=False,
        message=(
            "Audit markdown DB path matches configured SQLite"
            if ok
            else f"Path drift: audit has {recorded}, config has {actual}"
        ),
        details={"audit_path": str(recorded), "config_path": str(actual)},
    )
