"""Evidence URL format and HTTP probing for operational trust."""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

from .operational_trust_csv import dedupe_urls, read_csv_rows
from .operational_trust_types import TrustCheck


def is_valid_http_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return False
    p = urlparse(u)
    return p.scheme in ("http", "https") and bool(p.netloc)


def probe_url(url: str, *, timeout: float, method: str = "HEAD") -> tuple[bool, str]:
    """Return (ok, reason)."""
    from origenlab_email_pipeline.operational_trust import urlopen

    if not is_valid_http_url(url):
        return False, "invalid_or_empty_url"
    req = Request(url, method=method, headers={"User-Agent": "origenlab-operational-trust/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if code is not None and 200 <= int(code) < 400:
                return True, f"ok:{code}"
            return False, f"http:{code}"
    except HTTPError as e:
        if method == "HEAD" and e.code in (403, 405, 501):
            return probe_url(url, timeout=timeout, method="GET")
        return False, f"http_error:{e.code}"
    except URLError as e:
        return False, f"url_error:{e.reason!s}"
    except Exception as e:
        return False, f"error:{type(e).__name__}"


def check_urls_batch(
    urls: list[str],
    *,
    timeout: float,
    max_failures: int,
    max_fail_ratio: float | None = None,
) -> TrustCheck:
    checked = 0
    failures: list[dict[str, str]] = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        checked += 1
        ok, reason = probe_url(u, timeout=timeout)
        if not ok:
            failures.append({"url": u[:500], "reason": reason})
    n_fail = len(failures)
    ratio = (n_fail / checked) if checked else 0.0
    over_n = n_fail > max_failures
    over_ratio = max_fail_ratio is not None and checked > 0 and ratio > max_fail_ratio
    ok = checked > 0 and not over_n and not over_ratio
    return TrustCheck(
        "evidence_url_http",
        ok=ok,
        critical=True,
        message=(
            f"URL checks: {checked} checked, {n_fail} failed (limit {max_failures}"
            + (f", ratio limit {max_fail_ratio}" if max_fail_ratio is not None else "")
            + ")"
        ),
        details={
            "checked": checked,
            "failures": failures[:50],
            "failure_count": n_fail,
            "failure_ratio": ratio,
        },
    )


def collect_urls_from_csvs(
    paths_and_columns: list[tuple[Path, list[str]]],
) -> list[str]:
    urls: list[str] = []
    for path, cols in paths_and_columns:
        for r in read_csv_rows(path):
            for c in cols:
                v = (r.get(c) or "").strip()
                if v:
                    urls.append(v)
    return urls


def check_evidence_url_formats(urls: list[str]) -> TrustCheck:
    """Reject non-http(s) URL strings collected from CSV columns (mailto:, relative, etc.)."""
    bad: list[str] = []
    for u in dedupe_urls(urls):
        if not is_valid_http_url(u):
            bad.append(u[:400])
    return TrustCheck(
        "evidence_url_format",
        ok=len(bad) == 0,
        critical=True,
        message="All collected evidence URLs use http(s) scheme with host"
        if not bad
        else f"Invalid URL format(s): {len(bad)} (showing first 5): {bad[:5]}",
        details={"invalid": bad[:30], "invalid_count": len(bad)},
    )
