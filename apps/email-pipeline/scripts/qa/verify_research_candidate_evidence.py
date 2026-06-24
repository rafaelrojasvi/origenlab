#!/usr/bin/env python3
"""Verify research candidate evidence with lightweight HTTP/content checks.

Safety:
- Read-only HTTP fetches only.
- No sending, no DB writes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_USER_AGENT = "OrigenLabEvidenceVerifier/1.0 (+https://origenlab.cl)"
WEAK_PATHS = {"", "/", "/index", "/home", "/inicio"}
GENERIC_LOCAL_PARTS = {
    "contacto",
    "contact",
    "info",
    "admision",
    "admisiones",
    "comunicaciones",
    "extension",
    "prensa",
}
RELEVANCE_KEYWORDS = (
    "laboratorio",
    "servicios",
    "analisis",
    "análisis",
    "microbiologia",
    "microbiología",
    "quimica",
    "química",
    "alimentos",
    "agua",
    "ambiente",
    "compras",
    "adquisiciones",
    "proveedores",
    "investigacion",
    "investigación",
    "transferencia tecnologica",
    "transferencia tecnológica",
    "planta piloto",
)
THIRD_PARTY_LEAD_HOST_TOKENS = (
    "apollo.io",
    "rocketreach.co",
    "zoominfo.com",
    "lusha.com",
    "signalhire.com",
    "contactout.com",
    "hunter.io",
)
WEBMAIL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "yahoo.com",
}


def _email_domain(email: str) -> str:
    e = str(email or "").strip().lower()
    return e.split("@", 1)[1] if "@" in e else ""


def _email_local(email: str) -> str:
    e = str(email or "").strip().lower()
    return e.split("@", 1)[0] if "@" in e else ""


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "").strip()).hostname or "").lower()
    except Exception:
        return ""


def _path(url: str) -> str:
    try:
        return (urlparse(str(url or "").strip()).path or "").strip().lower()
    except Exception:
        return ""


def _specific_source(url: str) -> bool:
    p = _path(url)
    if p in WEAK_PATHS:
        return False
    if p.endswith(".pdf"):
        return True
    return len(p.strip("/")) > 1


def _token_overlap(a: str, b: str) -> bool:
    ta = {x for x in a.replace("-", ".").split(".") if len(x) >= 4}
    tb = {x for x in b.replace("-", ".").split(".") if len(x) >= 4}
    return bool(ta & tb)


def _is_third_party_lead_host(host: str) -> bool:
    h = str(host or "").lower()
    return any(tok in h for tok in THIRD_PARTY_LEAD_HOST_TOKENS)


def _strip_html_to_text(content: bytes) -> str:
    from origenlab_email_pipeline.parse_mbox import html_to_text

    txt = html_to_text(content.decode("utf-8", errors="ignore"))
    return re.sub(r"\s+", " ", txt).strip()


def _extract_pdf_like_text(content: bytes) -> str:
    # Lightweight fallback without heavy PDF parsing dependency.
    txt = content.decode("latin1", errors="ignore")
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def fetch_source_text(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[int | None, str, str]:
    req = Request(
        url=url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout_seconds) as resp:
        status = int(getattr(resp, "status", 200) or 200)
        ctype = str(resp.headers.get("Content-Type") or "").lower()
        data = resp.read()
    if "pdf" in ctype or str(url).lower().endswith(".pdf"):
        return status, ctype, _extract_pdf_like_text(data)
    return status, ctype, _strip_html_to_text(data)


def verify_rows(
    rows: list[dict[str, str]],
    *,
    require_email_visible: bool,
    require_source_200: bool,
    require_relevance_keywords: bool,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=2):
        email = str(row.get("contact_email") or "").strip().lower()
        source_url = str(row.get("source_url") or "").strip()
        institution_name = str(row.get("institution_name") or "").strip()
        src_host = _host(source_url)
        src_path = _path(source_url)
        em_domain = _email_domain(email)
        local = _email_local(email)
        reasons: list[str] = []
        status: int | None = None
        text = ""
        fetch_error = ""

        if _is_third_party_lead_host(src_host):
            reasons.append("third_party_source_disallowed")
        else:
            try:
                status, _, text = fetch_source_text(
                    source_url,
                    timeout_seconds=timeout_seconds,
                    user_agent=user_agent,
                )
            except Exception as exc:
                fetch_error = str(exc)
                reasons.append("source_url_unreachable")

        if src_path in WEAK_PATHS:
            reasons.append("homepage_source_weak_evidence")
        if not _specific_source(source_url):
            reasons.append("source_page_not_specific")
        if (
            local in GENERIC_LOCAL_PARTS
            and src_path in WEAK_PATHS
        ):
            reasons.append("generic_contact_homepage_weak")
        if (
            src_host
            and em_domain
            and em_domain not in WEBMAIL_DOMAINS
            and not _token_overlap(src_host, em_domain)
        ):
            reasons.append("email_domain_institution_mismatch")

        low_text = str(text or "").lower()
        email_visible = email in low_text
        relevance_hit = any(k in low_text for k in RELEVANCE_KEYWORDS)

        if require_source_200 and status != 200:
            reasons.append("source_url_unreachable")
        if require_email_visible and not email_visible:
            reasons.append("email_not_visible_on_source")
        if require_relevance_keywords and not relevance_hit:
            reasons.append("source_lacks_lab_procurement_relevance")

        dedup_reasons = list(dict.fromkeys(reasons))
        out.append(
            {
                "source_line": str(idx),
                "institution_name": institution_name,
                "contact_email": email,
                "source_url": source_url,
                "http_status": "" if status is None else str(status),
                "email_visible_on_source": "1" if email_visible else "0",
                "relevance_keywords_present": "1" if relevance_hit else "0",
                "evidence_warning": ";".join(dedup_reasons),
                "evidence_ok": "1" if not dedup_reasons else "0",
                "fetch_error": fetch_error,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="Candidate CSV path.")
    ap.add_argument("--out-csv", type=Path, required=True, help="Verified evidence CSV output path.")
    ap.add_argument("--out-json", type=Path, default=None, help="Optional summary JSON output path.")
    ap.add_argument("--strict", action="store_true", help="Return non-zero when any evidence warning exists.")
    ap.add_argument("--require-email-visible", action="store_true")
    ap.add_argument("--require-source-200", action="store_true")
    ap.add_argument("--require-relevance-keywords", action="store_true")
    ap.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    ap.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"Input CSV not found: {args.input}", file=sys.stderr)
        return 2

    with args.input.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(f)]

    verified = verify_rows(
        rows,
        require_email_visible=bool(args.require_email_visible),
        require_source_200=bool(args.require_source_200),
        require_relevance_keywords=bool(args.require_relevance_keywords),
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        user_agent=str(args.user_agent),
    )
    warning_rows = [r for r in verified if str(r.get("evidence_warning") or "").strip()]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "source_line",
            "institution_name",
            "contact_email",
            "source_url",
            "http_status",
            "email_visible_on_source",
            "relevance_keywords_present",
            "evidence_warning",
            "evidence_ok",
            "fetch_error",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in verified:
            w.writerow(row)

    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input": str(args.input),
            "input_rows": len(rows),
            "warning_rows": len(warning_rows),
            "strict": bool(args.strict),
            "requirements": {
                "require_email_visible": bool(args.require_email_visible),
                "require_source_200": bool(args.require_source_200),
                "require_relevance_keywords": bool(args.require_relevance_keywords),
            },
            "warnings": warning_rows,
        }
        args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "input_rows": len(rows),
                "warning_rows": len(warning_rows),
                "ok": len(warning_rows) == 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.strict and warning_rows:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

