from __future__ import annotations

import re
from pathlib import Path

from .origenlab_context import (
    OrigenLabDraftingContext,
    default_commercial_policy_bullets,
)


def _email_pipeline_root() -> Path:
    # tatiana_copilot/ -> origenlab_email_pipeline/ -> src/ -> email-pipeline/
    return Path(__file__).resolve().parents[3]


def monorepo_root() -> Path:
    return _email_pipeline_root().parent.parent


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _ts_quoted_string(content: str, key: str) -> str | None:
    """Single-quoted string value for `key:` on same or next line."""
    m = re.search(rf"{re.escape(key)}:\s*(?:\n\s*)?'([^']*)'", content)
    return m.group(1).strip() if m else None


def _parse_company_ts(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in (
        "name",
        "geography",
        "oneLiner",
        "catalogNote",
        "primaryOffer",
        "heroSubtitle",
        "homeIntro",
    ):
        v = _ts_quoted_string(content, key)
        if v:
            out[key] = v
    aud: list[str] = []
    in_aud = False
    for line in content.splitlines():
        if "audience:" in line and "[" in line:
            in_aud = True
            continue
        if in_aud:
            if "]" in line:
                break
            m = re.search(r"'([^']*)'", line)
            if m:
                aud.append(m.group(1).strip())
    if aud:
        out["_audience"] = " · ".join(aud)
    return out


def _parse_contact_ts(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("email", "phoneDisplay", "locationPublic", "hours", "city", "country"):
        v = _ts_quoted_string(content, key)
        if v:
            out[key] = v
    return out


def _parse_services_ts(content: str) -> str:
    descs = re.findall(r"shortDescription:\s*'((?:\\'|[^'])*)'", content)
    if not descs:
        return ""
    return " · ".join(d.strip() for d in descs if d.strip())


def _parse_categories_ts(content: str) -> str:
    """Extract category name + buyerGuide lines (conservative)."""
    lines_out: list[str] = []
    parts = re.split(r"\n\s*\{\s*\n", content)
    for part in parts:
        nm = _ts_quoted_string(part, "name")
        bg = _ts_quoted_string(part, "buyerGuide")
        if nm and bg:
            short = bg.replace("\n", " ").strip()
            if len(short) > 220:
                short = short[:217].rstrip() + "…"
            lines_out.append(f"- {nm}: {short}")
    return "\n".join(lines_out)


def _parse_brands_ts(content: str) -> str:
    blocks: list[str] = []
    for m in re.finditer(
        r"id:\s*'([^']*)'\s*,\s*\n\s*name:\s*'([^']*)'.*?summary:\s*\n\s*'([^']*)'",
        content,
        re.DOTALL,
    ):
        name = m.group(2).strip()
        summary = m.group(3).strip().replace("\n", " ")
        if len(summary) > 180:
            summary = summary[:177].rstrip() + "…"
        blocks.append(f"- {name}: {summary}")
    return "\n".join(blocks)


def _parse_products_ts(content: str) -> str:
    items: list[str] = []
    for m in re.finditer(
        r"(?:name:\s*'([^']*)'|name:\s*\"([^\"]*)\")\s*,\s*\n\s*slug:\s*'([^']*)'.*?summary:\s*'([^']*)'",
        content,
        re.DOTALL,
    ):
        name = (m.group(1) or m.group(2) or "").strip()[:120]
        sm = (m.group(4) or "").replace("\n", " ").strip()
        if len(sm) > 120:
            sm = sm[:117].rstrip() + "…"
        if name:
            items.append(f"- {name}: {sm}")
    return "\n".join(items[:24])


def _build_signature(contact: dict[str, str], company_name: str, location: str) -> str:
    email = contact.get("email", "")
    phone = contact.get("phoneDisplay", "")
    hours = contact.get("hours", "")
    return (
        "Saludos cordiales,\n\n"
        f"{company_name}\n"
        f"{location}\n"
        f"Correo: {email}\n"
        f"Tel. / WhatsApp: {phone}\n"
        f"Horario: {hours}"
    )


def load_origenlab_drafting_context(
    *,
    repo_root: Path | None = None,
) -> OrigenLabDraftingContext:
    """
    Load OrigenLab facts from monorepo web `src/data/*.ts` only (no network).

    Missing files yield empty strings for those sections — never invented values.
    """
    root = repo_root or monorepo_root()
    web_data = root / "apps" / "web" / "src" / "data"
    sources: list[str] = []

    company_raw = _read_text(web_data / "company.ts")
    contact_raw = _read_text(web_data / "contact.ts")
    services_raw = _read_text(web_data / "services.ts")
    categories_raw = _read_text(web_data / "categories.ts")
    brands_raw = _read_text(web_data / "brands.ts")
    products_raw = _read_text(web_data / "products.ts")

    company: dict[str, str] = _parse_company_ts(company_raw) if company_raw else {}
    contact = _parse_contact_ts(contact_raw) if contact_raw else {}
    if company_raw:
        sources.append(str(web_data / "company.ts"))
    if contact_raw:
        sources.append(str(web_data / "contact.ts"))
    if services_raw:
        sources.append(str(web_data / "services.ts"))
    if categories_raw:
        sources.append(str(web_data / "categories.ts"))
    if brands_raw:
        sources.append(str(web_data / "brands.ts"))
    if products_raw:
        sources.append(str(web_data / "products.ts"))

    company_name = company.get("name", "").strip() or "OrigenLab"
    geography = company.get("geography", "").strip() or "Chile"
    base = contact.get("locationPublic") or ""
    if not base and contact.get("city"):
        base = f"{contact['city']}, {contact.get('country', 'Chile')}"

    one_liner = company.get("oneLiner", "").strip()
    catalog_note = company.get("catalogNote", "").strip()
    audience = company.get("_audience", "")

    services_summary = _parse_services_ts(services_raw) if services_raw else ""
    categories_summary = _parse_categories_ts(categories_raw) if categories_raw else ""

    brands_part = _parse_brands_ts(brands_raw) if brands_raw else ""
    products_part = _parse_products_ts(products_raw) if products_raw else ""
    bcparts = [p for p in (brands_part, products_part) if p.strip()]
    brands_products = "\n".join(bcparts) if bcparts else ""

    sig = _build_signature(
        contact,
        company_name,
        base or f"{contact.get('city', 'Valdivia')}, {contact.get('country', 'Chile')}",
    )

    policy = default_commercial_policy_bullets()

    return OrigenLabDraftingContext(
        company_name=company_name,
        geography=geography,
        base_location=base,
        positioning_one_liner=one_liner,
        catalog_note=catalog_note,
        audience_lines=tuple(audience.split(" · ")) if audience else (),
        contact_email=contact.get("email", "").strip(),
        contact_phone=contact.get("phoneDisplay", "").strip(),
        location_public=base,
        hours=contact.get("hours", "").strip(),
        services_summary=services_summary,
        categories_summary=categories_summary,
        brands_products_summary=brands_products,
        commercial_policy_bullets=policy,
        approved_signature_block=sig,
        fact_sources=tuple(sources),
    )
