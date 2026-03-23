"""Match lead_master to organization_master and contact_master.

Writes lead_matches_existing_orgs and lead_matches_existing_contacts.
Read-only from mart tables.
"""

from __future__ import annotations

import json
import re
import sqlite3

from origenlab_email_pipeline.org_normalize import is_junk_org_name, normalize_org_name
from origenlab_email_pipeline.pipeline_run_recorder import now_iso


def _normalize_name_for_match(name: str | None) -> str:
    """Lowercase, strip, remove common suffixes for simple name comparison."""
    if not name or not name.strip():
        return ""
    s = name.lower().strip()
    for suffix in (" s.a.", " sa", " spa", " ltda", " s.a", " spa.", " ltda."):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_leads_to_mart(
    conn: sqlite3.Connection,
    *,
    pipeline_run_id: int | None = None,
) -> tuple[int, int]:
    """Match leads to mart orgs and contacts.

    Clears and repopulates lead_matches_existing_orgs and lead_matches_existing_contacts.
    Returns (org_match_rows_written, contact_match_rows_written).
    """
    created_at = now_iso()

    try:
        conn.execute("SELECT 1 FROM organization_master LIMIT 1")
    except sqlite3.OperationalError:
        conn.rollback()
        return (0, 0)

    conn.execute("DELETE FROM lead_matches_existing_orgs")
    conn.execute("DELETE FROM lead_matches_existing_contacts")
    org_count = 0
    contact_count = 0

    domain_to_org: dict[str, tuple[str, str]] = {}
    for row in conn.execute(
        "SELECT domain, organization_name_guess FROM organization_master WHERE domain IS NOT NULL AND domain != ''"
    ):
        d, name = (row[0] or "").strip().lower(), (row[1] or "").strip()
        if d:
            domain_to_org[d] = (d, name)

    name_to_org: dict[str, tuple[str, str]] = {}
    for row in conn.execute(
        "SELECT domain, organization_name_guess FROM organization_master WHERE organization_name_guess IS NOT NULL"
    ):
        d, name = (row[0] or "").strip(), (row[1] or "").strip()
        key = _normalize_name_for_match(name)
        if key and key not in name_to_org:
            name_to_org[key] = (d or "", name)

    # contact_master: email (PK) is compared to lead email_norm
    contacts_by_email: dict[str, tuple[str, str, str, str]] = {}
    try:
        for row in conn.execute(
            "SELECT email, contact_name_best, domain, organization_name_guess FROM contact_master"
        ):
            em = (row[0] or "").strip().lower()
            if em:
                contacts_by_email[em] = (
                    row[0] or "",
                    row[1] or "",
                    row[2] or "",
                    row[3] or "",
                )
    except sqlite3.OperationalError:
        contacts_by_email = {}

    leads = conn.execute(
        """
        SELECT id, domain, org_name, contact_name, email_norm, domain_norm, org_name_norm
        FROM lead_master
        """
    ).fetchall()

    for row in leads:
        lead_id = row[0]
        lead_domain = (row[1] or "").strip().lower()
        lead_org_name = (row[2] or "").strip()
        lead_contact_name = row[3] or ""
        email_norm = (row[4] or "").strip().lower() if row[4] else ""
        domain_norm = (row[5] or "").strip().lower() if row[5] else ""

        # Prefer normalized domain for org lookup when raw domain empty.
        eff_domain = domain_norm or lead_domain

        # ---- org-level (domain then normalized org name) ----
        if eff_domain and eff_domain in domain_to_org:
            matched_domain, matched_org_name = domain_to_org[eff_domain]
            evid = {
                "rule": "domain_exact",
                "source": "organization_master",
                "lead_domain_raw": lead_domain,
                "lead_domain_norm": domain_norm or None,
                "matched_organization_domain": matched_domain,
                "mart_organization_name_guess": matched_org_name,
            }
            conn.execute(
                """
                INSERT INTO lead_matches_existing_orgs
                (lead_id, matched_domain, matched_org_name, match_type, confidence_score,
                 already_in_archive_flag, pipeline_run_id, evidence_json)
                VALUES (?, ?, ?, 'domain', 1.0, 1, ?, ?)
                """,
                (lead_id, matched_domain, matched_org_name, pipeline_run_id, json.dumps(evid, ensure_ascii=False)),
            )
            org_count += 1
        else:
            key = _normalize_name_for_match(lead_org_name)
            if key and key in name_to_org:
                matched_domain, matched_org_name = name_to_org[key]
                evid = {
                    "rule": "org_name_normalized",
                    "source": "organization_master",
                    "lead_org_name_raw": lead_org_name,
                    "lead_org_name_normalized_key": key,
                    "matched_organization_domain": matched_domain,
                    "mart_organization_name_guess": matched_org_name,
                }
                conn.execute(
                    """
                    INSERT INTO lead_matches_existing_orgs
                    (lead_id, matched_domain, matched_org_name, match_type, confidence_score,
                     already_in_archive_flag, pipeline_run_id, evidence_json)
                    VALUES (?, ?, ?, 'name_fuzzy', 0.7, 1, ?, ?)
                    """,
                    (lead_id, matched_domain or "", matched_org_name, pipeline_run_id, json.dumps(evid, ensure_ascii=False)),
                )
                org_count += 1

        # ---- contact-level: exact email ----
        if email_norm and email_norm in contacts_by_email:
            full_email, cname, cdom, corg_guess = contacts_by_email[email_norm]
            evid = {
                "rule": "contact_email_exact",
                "source": "contact_master",
                "lead_email_norm": email_norm,
                "matched_contact_email": full_email,
                "contact_master_domain": cdom,
                "contact_organization_name_guess": corg_guess,
            }
            conn.execute(
                """
                INSERT INTO lead_matches_existing_contacts
                (lead_id, matched_contact_email, matched_contact_name, matched_domain, match_type,
                 confidence_score, already_in_archive_flag, evidence_json, pipeline_run_id, created_at)
                VALUES (?, ?, ?, ?, 'contact_email_exact', 1.0, 1, ?, ?, ?)
                """,
                (
                    lead_id,
                    full_email,
                    cname or None,
                    cdom or None,
                    json.dumps(evid, ensure_ascii=False),
                    pipeline_run_id,
                    created_at,
                ),
            )
            contact_count += 1
            continue

        # ---- contact-level fallback: same domain + normalized contact name ----
        if (
            domain_norm
            and not is_junk_org_name(lead_contact_name)
            and len(normalize_org_name(lead_contact_name)) >= 4
        ):
            ln = normalize_org_name(lead_contact_name)
            found = False
            for crow in conn.execute(
                "SELECT email, contact_name_best, domain FROM contact_master WHERE lower(domain) = ?",
                (domain_norm,),
            ):
                cemail, cbest, cdom = crow[0] or "", crow[1] or "", crow[2] or ""
                if normalize_org_name(cbest) == ln:
                    evid = {
                        "rule": "domain_plus_contact_name_normalized",
                        "source": "contact_master",
                        "lead_domain_norm": domain_norm,
                        "lead_contact_name_raw": lead_contact_name,
                        "lead_contact_name_normalized": ln,
                        "matched_contact_email": cemail,
                        "matched_contact_name_best": cbest,
                        "matched_domain": cdom,
                    }
                    conn.execute(
                        """
                        INSERT INTO lead_matches_existing_contacts
                        (lead_id, matched_contact_email, matched_contact_name, matched_domain, match_type,
                         confidence_score, already_in_archive_flag, evidence_json, pipeline_run_id, created_at)
                        VALUES (?, ?, ?, ?, 'domain_contact_name', 0.72, 1, ?, ?, ?)
                        """,
                        (
                            lead_id,
                            cemail,
                            cbest or None,
                            cdom or None,
                            json.dumps(evid, ensure_ascii=False),
                            pipeline_run_id,
                            created_at,
                        ),
                    )
                    contact_count += 1
                    found = True
                    break
            if found:
                continue

    conn.commit()
    return (org_count, contact_count)
