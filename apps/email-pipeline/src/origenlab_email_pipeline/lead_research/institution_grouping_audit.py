"""Read-only institution / organization grouping audit (Chile-focused).

Compares ``contact_master`` / ``organization_master`` to suppression and outreach sidecars.
Does not mutate SQLite, Gmail, or Postgres.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain

_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com", "live.cl",
    "yahoo.com", "yahoo.es", "icloud.com", "me.com", "msn.com", "protonmail.com",
    "gmx.com", "mail.com",
})

_GENERIC_LOCALS = frozenset({
    "info", "contacto", "contact", "ventas", "compras", "adquisiciones", "administracion",
    "recepcion", "secretaria", "laboratorio", "lab", "comercial", "servicioalcliente",
    "atencion", "atencionalcliente", "ventas", "marketing", "soporte", "help", "office",
})

DOMAIN_INVENTORY_FIELDS = [
    "domain",
    "current_org_name",
    "org_name_variants",
    "contact_count",
    "sent_count",
    "received_count",
    "reply_count",
    "bounce_count",
    "suppression_count",
    "contacted_count",
    "lead_count",
    "prospect_count",
    "supplier_flag",
    "likely_sector",
    "likely_region",
    "source_tables",
    "confidence",
    "notes",
]

COLLISION_FIELDS = [
    "collision_type",
    "domain",
    "org_names",
    "contact_count",
    "confidence",
    "notes",
]

INSTITUTION_CANDIDATE_FIELDS = [
    "canonical_institution_name",
    "domains",
    "aliases",
    "contact_count",
    "sent_count",
    "received_count",
    "replies",
    "bounces",
    "active_cases",
    "last_contact_date",
    "classification_guess",
    "sector_guess",
    "confidence",
    "review_reason",
]

GENERIC_MAILBOX_FIELDS = [
    "email",
    "domain",
    "org_guess",
    "generic_type",
    "sent_count",
    "reply_count",
    "bounce_suppression_state",
    "recommended_handling",
]

SUPPLIER_VENDOR_FIELDS = [
    "domain",
    "org_name",
    "contact_count",
    "supplier_source",
    "sector_guess",
    "recommended_handling",
]

_SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "university_research": ("universidad", "udec", "uchile", "puc.", "usach", "uach", "edu"),
    "hospital_clinic": ("hospital", "clinica", "clínica", "salud", "minsal"),
    "pharma_cosmetic": ("pharma", "farma", "laboratorio", "cosmetic", "novonordisk", "bayer"),
    "food_agro_qc": ("agro", "aliment", "food", "frut", "pesqu", "vinic"),
    "environmental_lab": ("ambient", "medioambiente", "eula", "idiem"),
    "supplier_vendor": ("supplier", "proveedor", "import", "distrib", "equipos", "hielscher"),
    "logistics_admin": ("aduana", "logist", "transport", "courier", "dhl", "fedex"),
    "public_tender": ("licit", "chilecompra", "mercado publico"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm_org(name: str | None) -> str:
    if not name:
        return ""
    s = re.sub(r"\s+", " ", str(name).strip().lower())
    s = re.sub(r"[^a-z0-9áéíóúñü\s]", "", s)
    return s


def _local_part(email: str) -> str:
    found = emails_in(email.strip().lower())
    if not found:
        return ""
    return found[0].split("@", 1)[0]


def _guess_sector(domain: str, org_name: str, org_type: str) -> str:
    hay = f"{domain} {org_name} {org_type}".lower()
    for sector, keys in _SECTOR_KEYWORDS.items():
        if any(k in hay for k in keys):
            return sector
    if domain.endswith(".cl") and "lab" in hay:
        return "private_lab"
    return "unknown_review"


def _guess_classification(
    *,
    supplier: bool,
    outbound: int,
    inbound: int,
    org_type: str,
    suppressed: bool,
) -> str:
    if supplier or "supplier" in (org_type or "").lower() or "proveedor" in (org_type or "").lower():
        return "supplier"
    if "logist" in (org_type or "").lower() or "admin" in (org_type or "").lower():
        return "admin"
    if suppressed and outbound == 0:
        return "noise"
    if outbound >= 3 or inbound >= 2:
        return "client"
    if outbound > 0:
        return "prospect"
    return "unknown"


def _confidence(
    *,
    org_variants: int,
    free_email: bool,
    supplier: bool,
    contact_count: int,
    has_org_master: bool,
) -> str:
    if free_email:
        return "low"
    if supplier:
        return "high"
    if org_variants > 1:
        return "low"
    if contact_count >= 2 and has_org_master:
        return "high"
    if contact_count >= 1 and has_org_master:
        return "medium"
    return "needs_review"


def connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


@dataclass(frozen=True)
class InstitutionGroupingAuditResult:
    summary: dict[str, Any]
    out_dir: Path


def run_institution_grouping_audit(
    conn: sqlite3.Connection,
    *,
    sqlite_path: Path,
    out_dir: Path,
    generated_at: str | None = None,
) -> InstitutionGroupingAuditResult:
    generated = generated_at or _utc_now()
    out_dir.mkdir(parents=True, exist_ok=True)

    org_master: dict[str, dict] = {}
    if _table_exists(conn, "organization_master"):
        for row in conn.execute(
            """
            SELECT domain, organization_name_guess, organization_type_guess,
                   total_emails, total_contacts, last_seen_at
            FROM organization_master
            """
        ):
            dom = str(row["domain"] or "").strip().lower()
            if dom:
                org_master[dom] = dict(row)

    supplier_domains: set[str] = set()
    if _table_exists(conn, "supplier_master"):
        for row in conn.execute(
            "SELECT domain_norm FROM supplier_master WHERE COALESCE(is_exclusion,0) = 1"
        ):
            if row[0]:
                supplier_domains.add(str(row[0]).strip().lower())
    if _table_exists(conn, "contact_domain_suppression"):
        for row in conn.execute("SELECT domain_norm FROM contact_domain_suppression"):
            if row[0]:
                supplier_domains.add(str(row[0]).strip().lower())

    suppressed_emails: set[str] = set()
    bounce_emails: set[str] = set()
    if not _table_exists(conn, "contact_email_suppression"):
        pass
    else:
        for row in conn.execute(
            "SELECT email, suppression_reason_code FROM contact_email_suppression"
        ):
            em = str(row[0] or "").strip().lower()
            if em:
                suppressed_emails.add(em)
                if str(row[1] or "").startswith("bounce"):
                    bounce_emails.add(em)

    contacted_emails: set[str] = set()
    if _table_exists(conn, "outreach_contact_state"):
        for row in conn.execute(
            """
            SELECT contact_email_norm FROM outreach_contact_state
            WHERE LOWER(TRIM(state)) IN ('contacted','replied','snoozed')
            """
        ):
            em = str(row[0] or "").strip().lower()
            if em:
                contacted_emails.add(em)

    lead_by_domain: dict[str, int] = Counter()
    if _table_exists(conn, "lead_master"):
        for row in conn.execute(
            """
            SELECT domain_norm, COUNT(*) FROM lead_master
            WHERE domain_norm IS NOT NULL AND TRIM(domain_norm) != ''
            GROUP BY domain_norm
            """
        ):
            lead_by_domain[str(row[0]).lower()] = int(row[1])

    prospect_by_domain: dict[str, int] = Counter()
    if _table_exists(conn, "lead_research_prospect"):
        for row in conn.execute(
            """
            SELECT domain, COUNT(*) FROM lead_research_prospect
            WHERE is_active=1 AND domain IS NOT NULL GROUP BY domain
            """
        ):
            prospect_by_domain[str(row[0]).lower()] = int(row[1])

    domain_rows: dict[str, dict] = defaultdict(lambda: {
        "org_names": Counter(),
        "org_types": Counter(),
        "contacts": [],
        "outbound": 0,
        "inbound": 0,
    })

    contacts_without_org = 0
    generic_contacts = 0
    total_contacts = 0

    if not _table_exists(conn, "contact_master"):
        raise RuntimeError("contact_master table required for institution grouping audit")

    for row in conn.execute(
        """
        SELECT email, domain, organization_name_guess, organization_type_guess,
               outbound_emails, inbound_emails, last_seen_at
        FROM contact_master
        """
    ):
        total_contacts += 1
        email = str(row["email"] or "").strip().lower()
        dom = str(row["domain"] or "").strip().lower() or (domain_of(email) if email else "")
        org = str(row["organization_name_guess"] or "").strip()
        if not org:
            contacts_without_org += 1
        local = _local_part(email)
        if local in _GENERIC_LOCALS or local.startswith("laboratorio"):
            generic_contacts += 1
        if not dom:
            continue
        bucket = domain_rows[dom]
        if org:
            bucket["org_names"][org] += 1
        otype = str(row["organization_type_guess"] or "").strip()
        if otype:
            bucket["org_types"][otype] += 1
        bucket["contacts"].append(email)
        bucket["outbound"] += int(row["outbound_emails"] or 0)
        bucket["inbound"] += int(row["inbound_emails"] or 0)
        if row["last_seen_at"]:
            bucket.setdefault("last_seen", str(row["last_seen_at"]))

    domain_inventory: list[dict] = []
    for dom in sorted(domain_rows.keys()):
        data = domain_rows[dom]
        org_variants = list(data["org_names"].keys())
        primary_org = org_variants[0] if len(org_variants) == 1 else (
            data["org_names"].most_common(1)[0][0] if data["org_names"] else ""
        )
        om = org_master.get(dom, {})
        if not primary_org and om:
            primary_org = str(om.get("organization_name_guess") or "")
        org_type = (
            data["org_types"].most_common(1)[0][0] if data["org_types"] else str(om.get("organization_type_guess") or "")
        )
        contact_count = len(data["contacts"])
        supp_count = sum(1 for e in data["contacts"] if e in suppressed_emails)
        bounce_count = sum(1 for e in data["contacts"] if e in bounce_emails)
        contacted_count = sum(1 for e in data["contacts"] if e in contacted_emails)
        is_supplier = dom in supplier_domains or is_supplier_email_domain(f"x@{dom}", supplier_domains)
        free = dom in _FREE_EMAIL_DOMAINS
        conf = _confidence(
            org_variants=len(org_variants),
            free_email=free,
            supplier=is_supplier,
            contact_count=contact_count,
            has_org_master=dom in org_master,
        )
        sources = ["contact_master"]
        if dom in org_master:
            sources.append("organization_master")
        if lead_by_domain.get(dom):
            sources.append("lead_master")
        if prospect_by_domain.get(dom):
            sources.append("lead_research_prospect")
        if is_supplier:
            sources.append("supplier_master")

        domain_inventory.append({
            "domain": dom,
            "current_org_name": primary_org,
            "org_name_variants": " | ".join(sorted(org_variants)[:8]),
            "contact_count": contact_count,
            "sent_count": data["outbound"],
            "received_count": data["inbound"],
            "reply_count": data["inbound"],
            "bounce_count": bounce_count,
            "suppression_count": supp_count,
            "contacted_count": contacted_count,
            "lead_count": lead_by_domain.get(dom, 0),
            "prospect_count": prospect_by_domain.get(dom, 0),
            "supplier_flag": is_supplier,
            "likely_sector": _guess_sector(dom, primary_org, org_type),
            "likely_region": "",
            "source_tables": ";".join(sorted(set(sources))),
            "confidence": conf,
            "notes": "free_email_domain" if free else ("multi_org_name" if len(org_variants) > 1 else ""),
        })

    _write_csv(out_dir / "domain_org_inventory.csv", DOMAIN_INVENTORY_FIELDS, domain_inventory)

    # collisions
    collisions: list[dict] = []
    for row in domain_inventory:
        variants = [v.strip() for v in str(row["org_name_variants"]).split("|") if v.strip()]
        if len(variants) > 1:
            collisions.append({
                "collision_type": "domain_multiple_org_names",
                "domain": row["domain"],
                "org_names": row["org_name_variants"],
                "contact_count": row["contact_count"],
                "confidence": row["confidence"],
                "notes": "normalize alias or pick canonical org name",
            })

    org_to_domains: dict[str, set[str]] = defaultdict(set)
    for row in domain_inventory:
        key = _norm_org(row["current_org_name"])
        if key and row["domain"] not in _FREE_EMAIL_DOMAINS:
            org_to_domains[key].add(row["domain"])

    _skip_org_keys = frozenset({
        "net", "gov", "com", "cl", "ltda", "sa", "spa", "inc", "corp", "group", "mail", "email",
        "thermofisher", "laboratorio", "universidad", "hospital", "lab",
    })
    for norm_org, domains in sorted(org_to_domains.items(), key=lambda x: -len(x[1])):
        if len(norm_org) < 8 or norm_org in _skip_org_keys:
            continue
        if len(domains) > 1:
            dom_list = sorted(domains)
            if not _domains_likely_same_institution(dom_list):
                collisions.append({
                    "collision_type": "org_name_multiple_domains",
                    "domain": dom_list[0],
                    "org_names": norm_org,
                    "contact_count": "",
                    "confidence": "low",
                    "notes": f"domains: {' | '.join(dom_list[:12])}",
                })

    _write_csv(
        out_dir / "org_name_collision_review.csv",
        COLLISION_FIELDS,
        sorted(collisions, key=lambda r: (r["collision_type"], r["domain"])),
    )

    # institution candidates (domain-primary)
    candidates: list[dict] = []
    for row in domain_inventory:
        if row["domain"] in _FREE_EMAIL_DOMAINS:
            continue
        dom = row["domain"]
        classification = _guess_classification(
            supplier=bool(row["supplier_flag"]),
            outbound=int(row["sent_count"]),
            inbound=int(row["received_count"]),
            org_type=row.get("likely_sector", ""),
            suppressed=int(row["suppression_count"]) > 0,
        )
        review = []
        if row["confidence"] == "low":
            review.append("low_confidence_domain")
        if row["org_name_variants"] and "|" in str(row["org_name_variants"]):
            review.append("org_name_variants")
        if classification == "supplier":
            review.append("supplier_vendor")
        candidates.append({
            "canonical_institution_name": row["current_org_name"] or dom,
            "domains": dom,
            "aliases": row["org_name_variants"],
            "contact_count": row["contact_count"],
            "sent_count": row["sent_count"],
            "received_count": row["received_count"],
            "replies": row["reply_count"],
            "bounces": row["bounce_count"],
            "active_cases": row["contacted_count"],
            "last_contact_date": domain_rows[dom].get("last_seen", ""),
            "classification_guess": classification,
            "sector_guess": row["likely_sector"],
            "confidence": row["confidence"],
            "review_reason": ";".join(review) if review else "",
        })

    _write_csv(
        out_dir / "institution_candidates.csv",
        INSTITUTION_CANDIDATE_FIELDS,
        sorted(candidates, key=lambda r: (-int(r["sent_count"]), r["domains"])),
    )

    # generic mailbox review
    generic_rows: list[dict] = []
    for row in conn.execute(
        "SELECT email, domain, organization_name_guess, outbound_emails, inbound_emails FROM contact_master"
    ):
        email = str(row["email"] or "").strip().lower()
        local = _local_part(email)
        if local not in _GENERIC_LOCALS and not local.startswith("laboratorio"):
            continue
        dom = str(row["domain"] or "").strip().lower() or domain_of(email)
        sup = email in suppressed_emails
        generic_rows.append({
            "email": email,
            "domain": dom,
            "org_guess": row["organization_name_guess"],
            "generic_type": local,
            "sent_count": int(row["outbound_emails"] or 0),
            "reply_count": int(row["inbound_emails"] or 0),
            "bounce_suppression_state": "suppressed" if sup else ("bounce" if email in bounce_emails else ""),
            "recommended_handling": "route_by_domain_not_person; review org context before outreach",
        })
    _write_csv(
        out_dir / "generic_mailbox_review.csv",
        GENERIC_MAILBOX_FIELDS,
        sorted(generic_rows, key=lambda r: (r["domain"], r["email"])),
    )

    # supplier vendor review
    supplier_rows: list[dict] = []
    seen_dom: set[str] = set()
    for dom in sorted(supplier_domains):
        if dom in seen_dom:
            continue
        seen_dom.add(dom)
        inv = next((r for r in domain_inventory if r["domain"] == dom), None)
        supplier_rows.append({
            "domain": dom,
            "org_name": inv["current_org_name"] if inv else "",
            "contact_count": inv["contact_count"] if inv else 0,
            "supplier_source": "supplier_master_or_domain_suppression",
            "sector_guess": "supplier_vendor",
            "recommended_handling": "exclude_from_cold_prospect_institution_view",
        })
    for row in domain_inventory:
        if row["supplier_flag"] and row["domain"] not in seen_dom:
            seen_dom.add(row["domain"])
            supplier_rows.append({
                "domain": row["domain"],
                "org_name": row["current_org_name"],
                "contact_count": row["contact_count"],
                "supplier_source": "heuristic_or_mart",
                "sector_guess": "supplier_vendor",
                "recommended_handling": "exclude_from_cold_prospect_institution_view",
            })
    _write_csv(
        out_dir / "supplier_vendor_review.csv",
        SUPPLIER_VENDOR_FIELDS,
        sorted(supplier_rows, key=lambda r: r["domain"]),
    )

    domains_multi_org = sum(1 for r in domain_inventory if "|" in str(r.get("org_name_variants", "")))
    orgs_multi_domain = sum(1 for c in collisions if c["collision_type"] == "org_name_multiple_domains")
    high_conf = sum(1 for c in candidates if c["confidence"] == "high")
    needs_review = sum(1 for c in candidates if c["confidence"] in {"low", "needs_review", "medium"})

    contacted_domains = len({domain_of(e) for e in contacted_emails if domain_of(e)})
    suppressed_domain_count = len(supplier_domains)

    summary = {
        "total_organizations": len(org_master),
        "total_domains": len(domain_inventory),
        "total_contacts": total_contacts,
        "domains_with_multiple_org_names": domains_multi_org,
        "org_names_with_multiple_domains": orgs_multi_domain,
        "contacts_without_org": contacts_without_org,
        "contacts_with_generic_email": generic_contacts,
        "suppressed_domains_count": suppressed_domain_count,
        "contacted_domains_count": contacted_domains,
        "candidate_institution_groups_count": len(candidates),
        "high_confidence_groups_count": high_conf,
        "needs_review_groups_count": needs_review,
        "generated_at": generated,
        "sqlite_path": str(sqlite_path.resolve()),
    }
    (out_dir / "organization_grouping_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _write_markdown_docs(out_dir, summary, domain_inventory, candidates, collisions)
    (out_dir / "EXECUTIVE_SUMMARY.md").write_text(
        _executive_summary(summary, candidates, domain_inventory, collisions),
        encoding="utf-8",
    )
    return InstitutionGroupingAuditResult(summary=summary, out_dir=out_dir)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def print_headline_counts(summary: dict[str, Any], *, out_dir: Path) -> None:
    print("Institution grouping audit (read-only)")
    print(f"  sqlite: {summary['sqlite_path']}")
    print(f"  out:    {out_dir}")
    for key in (
        "total_organizations",
        "total_domains",
        "total_contacts",
        "domains_with_multiple_org_names",
        "org_names_with_multiple_domains",
        "contacts_with_generic_email",
        "contacted_domains_count",
        "suppressed_domains_count",
        "high_confidence_groups_count",
        "needs_review_groups_count",
        "candidate_institution_groups_count",
    ):
        print(f"  {key}: {summary[key]}")


def _domains_likely_same_institution(domains: list[str]) -> bool:
    """Heuristic: subdomains or shared registrable stem."""
    if len(domains) <= 1:
        return True
    stems = [d.split(".")[0] for d in domains]
    if len(set(stems)) == 1:
        return True
    return False


def _write_markdown_docs(
    out_dir: Path,
    summary: dict,
    domain_inventory: list[dict],
    candidates: list[dict],
    collisions: list[dict],
) -> None:
    sector_counts = Counter(c["sector_guess"] for c in candidates)
    lines = [
        "# Sector taxonomy proposal\n",
        "Compact taxonomy for institution grouping (aligns with SCHEMA_CLASSIFICATION_MODEL business_role + workflow).\n",
    ]
    taxonomy = {
        "university_research": ("Universidades y centros de investigación", "udec.cl, uchile, puc"),
        "private_lab": ("Laboratorios privados / QC industrial", "laboratorio, lab, analisis"),
        "hospital_clinic": ("Hospitales y clínicas", "hospital, clinica, salud"),
        "pharma_cosmetic": ("Farmacéutica y cosmética", "pharma, bayer, heel"),
        "food_agro_qc": ("Alimentos y agro QC", "agro, food, salmofood"),
        "environmental_lab": ("Laboratorio ambiental", "ambiental, eula, idiem"),
        "supplier_vendor": ("Proveedor / importador equipamiento", "supplier_master, exclusion list"),
        "logistics_admin": ("Logística / admin / courier", "aduana, transport"),
        "public_tender": ("Licitación / compra pública", "chilecompra, licitacion"),
        "unknown_review": ("Revisión manual", "gmail.com, colisiones de nombre"),
    }
    for key, (defn, examples) in taxonomy.items():
        n = sector_counts.get(key, 0)
        lines.append(f"\n## `{key}` ({n} domain-groups)\n")
        lines.append(f"- **Definición:** {defn}")
        lines.append(f"- **Ejemplos:** {examples}")
        lines.append("- **Incluir:** dominio corporativo .cl con evidencia de compra/lab en mart")
        lines.append("- **Excluir:** proveedores en `supplier_master`; buzones gmail/hotmail")
        lines.append(f"- **Etiqueta dashboard (ES):** {_spanish_label(key)}\n")

    (out_dir / "sector_taxonomy_proposal.md").write_text("\n".join(lines), encoding="utf-8")

    rules = """# Grouping rules proposal

Deterministic rules for institution grouping (read-only audit baseline).

## 1. Exact domain grouping (default)

- **Primary key:** registrable domain from `contact_master.domain` / `organization_master.domain`.
- **Reliable when:** one dominant `organization_name_guess`, ≥2 contacts or outbound>0, not supplier, not free-mail.

## 2. Known aliases (manual map — P1)

- Use `org_name_collision_review.csv` to add alias table (e.g. fundación vs fundacion, abbreviations).
- Do not auto-merge distinct domains without evidence.

## 3. Parent / subdomain

- Default: **do not auto-merge** `sub.domain.cl` with `domain.cl` unless alias table says so.
- Flag for review when org name matches but domains differ.

## 4. University department / lab

- Keep **domain-level** group; department emails (e.g. `lab@udec.cl`) roll up to university domain when domain is shared.
- Separate prospect rows when `lead_research` uses different `organization_name` on same domain → review queue.

## 5. Gmail / Hotmail / personal

- **Never** auto-group personal domains as institution.
- Show as `contact`-level only with `review_required`.

## 6. Supplier / noise exclusion

- Exclude `supplier_master.is_exclusion`, `contact_domain_suppression`, and mart `supplier_flag` from prospect institution KPIs.
- Warm-case `is_supplier_vendor_domain` list remains separate safety net.

## 7. When to require manual review

- Multiple org names per domain.
- One normalized org name on multiple unrelated domains.
- Generic mailboxes (`contacto@`, `ventas@`) — group by domain, not by mailbox name.
- Any send decision still uses suppression/outreach sidecars (golden rule).

## Alignment with SCHEMA_CLASSIFICATION_MODEL

| Layer | Institution audit uses |
| --- | --- |
| Evidence | `contact_master` email counts, `emails` indirectly |
| Safety | suppression/domain suppression — exclude from prospect institutions |
| Business | `organization_type_guess`, sector heuristics |
| Workflow | lead_research / outreach contacted |
| UI | derived institution read-model only — not new SoT |
"""
    (out_dir / "grouping_rules_proposal.md").write_text(rules, encoding="utf-8")

    cleanup = """# Institution grouping cleanup plan

## P0 — safety blockers

| Task | Why |
| --- | --- |
| Never group send eligibility from institution view alone | Same golden rule as Prospectos — use suppression/outreach gates |
| Exclude supplier domains from institution prospect KPIs | Prevent supplier clusters looking like buyers |

## P1 — grouping consistency

| Task | Why |
| --- | --- |
| Canonical alias table for top `org_name_collision_review` rows | Fixes multi-name / multi-domain confusion |
| Rebuild mart org guesses after alias map | `organization_master` is derived |
| Roll up generic mailboxes to domain institution | `generic_mailbox_review.csv` |

## P2 — dashboard institution view

| Task | Why |
| --- | --- |
| Read-model: institution ← domain + alias map | Mirror only; no new SQLite SoT |
| Spanish labels from sector taxonomy | Operator clarity |
| Show confidence + review_reason on each card | Avoid false certainty |

## P3 — future enrichment

| Task | Why |
| --- | --- |
| RUT / Chile registry enrichment | Not in current DB |
| LLM org normalization | Only with human approval |
| Parent-company graph | Out of scope for v1 |
"""
    (out_dir / "cleanup_plan.md").write_text(cleanup, encoding="utf-8")


def _spanish_label(sector: str) -> str:
    return {
        "university_research": "Universidad / investigación",
        "private_lab": "Laboratorio privado",
        "hospital_clinic": "Hospital / clínica",
        "pharma_cosmetic": "Farmacéutica / cosmética",
        "food_agro_qc": "Alimentos / agro QC",
        "environmental_lab": "Laboratorio ambiental",
        "supplier_vendor": "Proveedor / vendor",
        "logistics_admin": "Logística / administración",
        "public_tender": "Licitación pública",
        "unknown_review": "Revisar",
    }.get(sector, "Revisar")


def _executive_summary(
    summary: dict,
    candidates: list[dict],
    domain_inventory: list[dict],
    collisions: list[dict],
) -> str:
    top_sectors = Counter(c["sector_guess"] for c in candidates).most_common(8)
    good = sorted(
        [
            c
            for c in candidates
            if c["confidence"] == "high"
            and int(c["sent_count"]) >= 5
            and c["classification_guess"] in {"client", "prospect"}
            and c["domains"] not in _FREE_EMAIL_DOMAINS
        ],
        key=lambda c: -int(c["sent_count"]),
    )[:5]
    bad = sorted(
        [c for c in collisions if c["collision_type"] == "org_name_multiple_domains"],
        key=lambda c: -len(str(c.get("notes", ""))),
    )[:5]

    good_lines = "\n".join(
        f"- **{g['canonical_institution_name']}** (`{g['domains']}`) — {g['sector_guess']}, sent={g['sent_count']}"
        for g in good
    ) or "- (none at high confidence in sample)"
    bad_lines = "\n".join(
        f"- **{b['domain']}** — {b['notes'][:120]}"
        for b in bad
    ) or "- (see collision CSV)"

    return f"""# Institution grouping audit — executive summary

Generated: {summary['generated_at']}  
SQLite: `{summary['sqlite_path']}`  
Model: [`SCHEMA_CLASSIFICATION_MODEL.md`](../../../docs/pipeline/SCHEMA_CLASSIFICATION_MODEL.md)

## How good is current domain/org grouping?

**Good enough for domain-level mart analytics** (`organization_master` ≈ {summary['total_organizations']:,} domains).  
**Not yet good enough for automatic institution merge** without alias review: **{summary['domains_with_multiple_org_names']}** domains have multiple org names in mart contacts; **{summary['org_names_with_multiple_domains']}** org-name collision rows span unrelated domains (see collision CSV).

## Where it fails

- Generic mailboxes (`contacto@`, `ventas@`) — {summary['contacts_with_generic_email']:,} contacts need domain-level context.
- Free-email domains (gmail/hotmail) — must stay contact-level, not institution.
- Supplier/vendor domains mixed into mart — use `supplier_vendor_review.csv`.
- `lead_research` / post-send state can disagree with mart org guesses (see Prospectos drift audit).

## Top sectors (candidate groups)

{chr(10).join(f'- `{s}`: {n}' for s, n in top_sectors)}

## Is organization_master enough?

**As derived read-model input: yes.** As sole institution SoT: **no** — add alias map + confidence + exclusion rules before dashboard institution cards.

## Dashboard institutions safely?

**v1 read-only: yes**, with domain-primary cards, confidence badges, and no send actions.  
**Do not** imply send safety from institution classification alone.

## Recommended next steps

1. Review `org_name_collision_review.csv` — top 50 rows manual alias decisions.  
2. P1: small `institution_alias` table (domain → canonical_name).  
3. Keep suppliers out of prospect institution view.  
4. Re-run this audit after mart rebuild (`audit_institution_grouping.py`).

## Examples — good groups

{good_lines}

## Examples — ambiguous

{bad_lines}

## Headline counts

| Metric | Value |
| --- | ---: |
| Domains | {summary['total_domains']:,} |
| Contacts | {summary['total_contacts']:,} |
| High-confidence institution candidates | {summary['high_confidence_groups_count']:,} |
| Needs review | {summary['needs_review_groups_count']:,} |
| Collisions (CSV rows) | {len(collisions):,} |
"""
