"""
Voice / drafting-style email cohort helpers (historical OrigenLab outbound).

In practice, Tatiana Vivanco’s writing in this archive is usually associated with
mail sent from **labdelivery.cl** (older LabDelivery addresses). The pipeline does
not tag people by name; we cohort by **sender domain** and/or an optional address
allowlist.

Policy:
- **Domain list** (`config/voice_sender_domains.txt`, optional local override file,
  env `ORIGENLAB_VOICE_SENDER_DOMAINS`): include any message whose parsed From
  address ends with one of these domains.
- **Address allowlist** (optional): specific emails (e.g. personal aliases).
- **Text signals** (optional): From line or clean body contains “Tatiana” / “Vivanco”
  as a whole word, and the parsed sender domain is a **trusted company domain**
  (`INTERNAL_DOMAINS` ∪ voice domains). This catches signatures and display names
  not tied to labdelivery.cl alone. Does not use subject (too many client “Hola Tatiana”
  forwards would need different rules).
- A row matches if any enabled rule matches. Role mailboxes on origenlab.cl are
  excluded by default unless you opt in.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from origenlab_email_pipeline.business_filter_rules import INTERNAL_DOMAINS
from origenlab_email_pipeline.business_mart import domain_of, primary_sender_email

# Word-boundary matches (signatures, display names); not substring inside unrelated tokens.
_RE_TATIANA = re.compile(r"\btatiana\b", re.I)
_RE_VIVANCO = re.compile(r"\bvivanco\b", re.I)

# Lowercased addresses for shared / role mailboxes (extend as needed).
SHARED_MAILBOX_EMAILS: frozenset[str] = frozenset(
    {
        "contacto@origenlab.cl",
        "info@origenlab.cl",
        "ventas@origenlab.cl",
    }
)


def _norm_addr(s: str) -> str:
    return (s or "").strip().lower()


def _email_pipeline_root() -> Path:
    """`apps/email-pipeline` (parent of `src/origenlab_email_pipeline`)."""
    return Path(__file__).resolve().parents[2]


def _read_allowlist_file(path: Path) -> set[str]:
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a = _norm_addr(line.split()[0] if line else "")
        if a and "@" in a:
            out.add(a)
    return out


def _read_domain_lines_file(path: Path) -> set[str]:
    """One registrable domain per line (e.g. labdelivery.cl)."""
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0]
        token = token.lstrip("@")
        if "." in token and "@" not in token:
            out.add(token)
    return out


def default_allowlist_path() -> Path:
    """Gitignored convention: copy `config/tatiana_senders.example.txt` to this name."""
    return _email_pipeline_root() / "config" / "tatiana_senders.local.txt"


def default_voice_domains_path() -> Path:
    """Tracked defaults; optional gitignored `voice_sender_domains.local.txt` merges on top."""
    return _email_pipeline_root() / "config" / "voice_sender_domains.txt"


def local_voice_domains_override_path() -> Path:
    return _email_pipeline_root() / "config" / "voice_sender_domains.local.txt"


def load_voice_sender_domains() -> frozenset[str]:
    """
    Domains for the voice cohort (From address domain must match).

    Loads, in order (merged):
    - `config/voice_sender_domains.txt` (repo default; usually labdelivery.cl)
    - `config/voice_sender_domains.local.txt` if present (gitignored optional override)
    - ORIGENLAB_VOICE_SENDER_DOMAINS (comma-separated, e.g. labdelivery.cl,origenlab.cl)
    - ORIGENLAB_VOICE_SENDER_DOMAINS_FILE if set and exists
    """
    out: set[str] = set()
    tracked = default_voice_domains_path()
    if tracked.is_file():
        out.update(_read_domain_lines_file(tracked))
    local_dom = local_voice_domains_override_path()
    if local_dom.is_file():
        out.update(_read_domain_lines_file(local_dom))
    raw = os.environ.get("ORIGENLAB_VOICE_SENDER_DOMAINS", "").strip()
    if raw:
        for part in raw.split(","):
            p = part.strip().lower().lstrip("@")
            if p and "." in p and "@" not in p:
                out.add(p)
    path_raw = os.environ.get("ORIGENLAB_VOICE_SENDER_DOMAINS_FILE", "").strip()
    if path_raw:
        path = Path(path_raw).expanduser()
        if path.is_file():
            out.update(_read_domain_lines_file(path))
    return frozenset(out)


def trusted_domains_for_identity_mentions(voice_domains: frozenset[str]) -> frozenset[str]:
    """Company From-domains allowed when matching Tatiana/Vivanco text in headers/body."""
    internal = frozenset(x.lower().strip() for x in INTERNAL_DOMAINS)
    extra = frozenset(x.lower() for x in voice_domains)
    return internal | extra


def text_blob_mentions_tatiana_identity(*parts: str | None) -> bool:
    """True if any part contains whole-word Tatiana or Vivanco (signatures, display names)."""
    blob = "\n".join(p or "" for p in parts)
    if not blob.strip():
        return False
    return bool(_RE_TATIANA.search(blob) or _RE_VIVANCO.search(blob))


def sender_domain_matches_voice_domains(sender_header: str | None, domains: frozenset[str]) -> bool:
    if not domains:
        return False
    primary = primary_sender_email(sender_header or "")
    if not primary:
        return False
    dom = domain_of(primary)
    if not dom:
        return False
    d = dom.lower()
    for vd in domains:
        v = vd.lower().strip()
        if d == v or d.endswith("." + v):
            return True
    return False


def load_tatiana_allowlist() -> frozenset[str]:
    """
    Load allowlisted sender addresses (lowercase).

    Sources (merged in order):
    - ORIGENLAB_TATIANA_SENDERS: comma-separated list
    - ORIGENLAB_TATIANA_SENDERS_FILE: path to UTF-8 file, one address per line;
      lines starting with # and blank lines are skipped.
    - If still empty: `config/tatiana_senders.local.txt` under `apps/email-pipeline`
      (same format as the file above), if that path exists.
    """
    out: set[str] = set()
    raw = os.environ.get("ORIGENLAB_TATIANA_SENDERS", "").strip()
    if raw:
        for part in raw.split(","):
            a = _norm_addr(part)
            if a and "@" in a:
                out.add(a)
    path_raw = os.environ.get("ORIGENLAB_TATIANA_SENDERS_FILE", "").strip()
    if path_raw:
        path = Path(path_raw).expanduser()
        if path.is_file():
            out.update(_read_allowlist_file(path))
    if not out:
        local = default_allowlist_path()
        if local.is_file():
            out.update(_read_allowlist_file(local))
    return frozenset(out)


def sender_header_matches_allowlist(sender_header: str | None, allowlist: frozenset[str]) -> bool:
    if not allowlist:
        return False
    primary = primary_sender_email(sender_header or "")
    if not primary:
        return False
    return _norm_addr(primary) in allowlist


def is_shared_mailbox_sender(sender_header: str | None) -> bool:
    primary = primary_sender_email(sender_header or "")
    if not primary:
        return False
    return _norm_addr(primary) in SHARED_MAILBOX_EMAILS


def is_voice_candidate_row(
    sender_header: str | None,
    allowlist: frozenset[str],
    *,
    voice_domains: frozenset[str] | None = None,
    full_body_clean: str | None = None,
    top_reply_clean: str | None = None,
    include_tatiana_text_signals: bool = False,
    trusted_domains_for_text_signals: frozenset[str] | None = None,
    allow_shared_mailboxes: bool = False,
) -> bool:
    """
    True if the row matches the address allowlist, voice sender domains, and/or
    (when enabled) Tatiana/Vivanco mentions in From line or clean body while From
    domain is a trusted company domain.
    """
    voice_domains = voice_domains or frozenset()
    by_addr = sender_header_matches_allowlist(sender_header, allowlist)
    by_dom = sender_domain_matches_voice_domains(sender_header, voice_domains)
    by_mention = False
    if include_tatiana_text_signals:
        trusted = trusted_domains_for_text_signals or trusted_domains_for_identity_mentions(
            voice_domains
        )
        if sender_domain_matches_voice_domains(sender_header, trusted):
            by_mention = text_blob_mentions_tatiana_identity(
                sender_header,
                full_body_clean,
                top_reply_clean,
            )
    if not by_addr and not by_dom and not by_mention:
        return False
    if not allow_shared_mailboxes and is_shared_mailbox_sender(sender_header):
        return False
    return True


def hybrid_style_body(full_body_clean: str | None, top_reply_clean: str | None) -> str:
    """
    Choose text for style / voice use given Phase 2.2 fields.

    top_reply_clean strips reply chains and often removes trailing sign-offs
    (Saludos, Atentamente, …). full_body_clean keeps the full normalized body
    before reply-header cuts only — so closings usually remain there when the
    only difference is signature stripping.

    Heuristic:
    - If one side is empty, use the other.
    - If equal, use full (same content).
    - If full starts with top and the extra tail is small (≤280 chars), treat as
      sign-off / footer only → use full.
    - If full starts with top and the tail is large, treat as quoted thread → use top.
    - Otherwise fall back to length ratio: much shorter top → use top; else full.
    """
    f = (full_body_clean or "").strip()
    t = (top_reply_clean or "").strip()
    if not f:
        return t
    if not t:
        return f
    if t == f:
        return f
    if f.startswith(t):
        delta = len(f) - len(t)
        if delta <= 280:
            return f
        return t
    if len(f) <= len(t):
        return t
    ratio = len(t) / len(f)
    if ratio < 0.88:
        return t
    return f


# Subject hints for stratified sampling (case-insensitive).
_RE_REPLY = re.compile(r"^\s*(re|fw|fwd)\s*:", re.I)

def subject_is_reply_or_forward(subject: str | None) -> bool:
    return bool(subject and _RE_REPLY.search(subject))


def bucket_body_length(n: int) -> str:
    if n < 200:
        return "short_lt_200"
    if n < 400:
        return "med_200_399"
    return "long_ge_400"
