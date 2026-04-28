from __future__ import annotations

# -----------------------------------------------------------------------------
# SAFETY (break-glass): Can send real email to real recipients via Gmail API when
# not using dry-run / message-build-only modes. Operator-invoked only.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------

import argparse
import csv
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from origenlab_email_pipeline.gmail_send import build_gmail_message_with_inline_images, gmail_api_send_message
from origenlab_email_pipeline.gmail_workspace_oauth import load_credentials_for_gmail_imap

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)


def _default_token_path() -> Path:
    data_root = os.environ.get("ORIGENLAB_DATA_ROOT")
    if data_root:
        return Path(data_root) / "secrets" / "gmail_workspace_token.json"
    return Path.home() / ".origenlab" / "secrets" / "gmail_workspace_token.json"


def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(_normalize_email(value)))


def _read_recipients_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if "," in text or path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        out: list[str] = []
        for row in rows:
            normalized_row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
            for key in ("contact_email", "email", "to"):
                val = _normalize_email(normalized_row.get(key, ""))
                if val:
                    out.append(val)
                    break
        return out
    return [_normalize_email(line) for line in text.splitlines() if _normalize_email(line)]


def _collect_recipients(*, to_values: list[str], to_file: str | None) -> list[str]:
    out: list[str] = []
    for raw in to_values:
        em = _normalize_email(raw)
        if em:
            out.append(em)
    if to_file:
        out.extend(_read_recipients_file(Path(to_file).expanduser().resolve()))
    # Stable de-dup preserving first-seen order.
    deduped: list[str] = []
    seen: set[str] = set()
    for em in out:
        if em not in seen:
            deduped.append(em)
            seen.add(em)
    return deduped


def _collect_cc(*, cc_values: list[str]) -> list[str]:
    out: list[str] = []
    for raw in cc_values:
        em = _normalize_email(raw)
        if em:
            out.append(em)
    deduped: list[str] = []
    seen: set[str] = set()
    for em in out:
        if em not in seen:
            deduped.append(em)
            seen.add(em)
    return deduped


def main() -> int:
    # Ensure local `.env` is picked up when running ad-hoc scripts.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    parser = argparse.ArgumentParser(description="Send a local HTML email via Gmail API with inline CID images.")
    parser.add_argument(
        "--to",
        action="append",
        default=[],
        help="Recipient email (repeatable).",
    )
    parser.add_argument(
        "--cc",
        action="append",
        default=[],
        help="Cc address (repeatable). Used with --single-message or per-message sends (see --single-message).",
    )
    parser.add_argument(
        "--single-message",
        action="store_true",
        help="Send one Gmail message with all --to in To and all --cc in Cc (instead of one send per --to).",
    )
    parser.add_argument(
        "--to-file",
        default=None,
        help="Optional newline or CSV file with recipients (contact_email/email/to column for CSV).",
    )
    parser.add_argument(
        "--subject",
        default="OrigenLab · Equipos para laboratorio en Chile",
        help="Email subject",
    )
    parser.add_argument(
        "--html",
        required=True,
        help="Path to the HTML file to send",
    )
    parser.add_argument(
        "--from-email",
        default=os.environ.get("ORIGENLAB_GMAIL_WORKSPACE_USER", ""),
        help="Sender email (defaults to ORIGENLAB_GMAIL_WORKSPACE_USER)",
    )
    parser.add_argument(
        "--from-name",
        default="OrigenLab",
        help='Sender display name (e.g. "OrigenLab")',
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open browser for OAuth if token missing/expired (default: false)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate messages only; do not call Gmail API.",
    )
    parser.add_argument(
        "--test-recipient",
        default=None,
        help="If set, sends ALL messages to this recipient instead of real recipients.",
    )
    parser.add_argument(
        "--max-recipients",
        type=int,
        default=200,
        help="Safety cap for recipient count (default: 200).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop batch immediately if one send fails (default: continue and report).",
    )
    args = parser.parse_args()

    recipients = _collect_recipients(to_values=list(args.to), to_file=args.to_file)
    cc_list = _collect_cc(cc_values=list(args.cc))
    if not recipients:
        raise SystemExit("No recipients provided. Use --to and/or --to-file.")
    invalid = [em for em in recipients if not _is_valid_email(em)]
    if invalid:
        raise SystemExit(f"Invalid recipient email(s): {', '.join(invalid)}")
    invalid_cc = [em for em in cc_list if not _is_valid_email(em)]
    if invalid_cc:
        raise SystemExit(f"Invalid Cc email(s): {', '.join(invalid_cc)}")
    if int(args.max_recipients) <= 0:
        raise SystemExit("--max-recipients must be >= 1")
    party_count = len(recipients) + (len(cc_list) if args.single_message else 0)
    if args.single_message:
        check_count = party_count
    else:
        check_count = len(recipients)
    if check_count > int(args.max_recipients):
        raise SystemExit(
            f"Recipient count {check_count} exceeds --max-recipients={int(args.max_recipients)}."
        )

    test_recipient = _normalize_email(args.test_recipient or "")
    if test_recipient and not _is_valid_email(test_recipient):
        raise SystemExit(f"Invalid --test-recipient email: {test_recipient}")

    client_json = os.environ.get("ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON")
    if not client_json:
        raise SystemExit("Missing ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON env var (path to OAuth client JSON).")

    token_json = Path(os.environ.get("ORIGENLAB_GMAIL_TOKEN_JSON", str(_default_token_path())))

    sender_email = args.from_email.strip()
    if not sender_email:
        raise SystemExit("Missing sender email. Set ORIGENLAB_GMAIL_WORKSPACE_USER or pass --from-email.")

    from_name = (args.from_name or "").strip()
    sender_header = f"{from_name} <{sender_email}>" if from_name else sender_email

    html_path = Path(args.html).expanduser().resolve()
    html = html_path.read_text(encoding="utf-8")

    creds = None
    if not args.dry_run:
        creds = load_credentials_for_gmail_imap(
            client_secrets_json=Path(client_json).expanduser().resolve(),
            token_json=token_json.expanduser().resolve(),
            open_browser=bool(args.open_browser),
        )

    sent = 0
    failed: list[str] = []

    if args.single_message:
        real_tos = list(recipients)
        if test_recipient:
            effective_tos = [test_recipient]
            effective_cc_list: list[str] = []
        else:
            effective_tos = real_tos
            effective_cc_list = cc_list
        msg, inline_images = build_gmail_message_with_inline_images(
            sender_email=sender_header,
            to_emails=effective_tos,
            cc_emails=effective_cc_list or None,
            subject=args.subject,
            html=html,
            html_dir=html_path.parent,
        )
        if args.dry_run:
            print(
                f"[DRY RUN] single_message real_to={','.join(real_tos)} "
                f"effective_to={','.join(effective_tos)} "
                f"cc_requested={','.join(cc_list) if cc_list else '(none)'} "
                f"effective_cc={','.join(effective_cc_list) if effective_cc_list else '(none)'} "
                f"inline_images={len(inline_images)}"
            )
        else:
            assert creds is not None
            try:
                result = gmail_api_send_message(access_token=creds.token, raw_message_bytes=msg.as_bytes())
                sent = 1
                print(
                    f"[SENT] single_message real_to={','.join(real_tos)} "
                    f"effective_to={','.join(effective_tos)} message_id={result.get('id')} "
                    f"inline_images={len(inline_images)}"
                )
            except Exception as exc:
                failed.extend(real_tos)
                print(f"[ERROR] single_message real_to={','.join(real_tos)}: {exc}")
    else:
        if cc_list:
            raise SystemExit("--cc requires --single-message (or omit --cc).")
        for idx, real_to in enumerate(recipients, start=1):
            effective_to = test_recipient or real_to
            msg, inline_images = build_gmail_message_with_inline_images(
                sender_email=sender_header,
                to_emails=effective_to,
                subject=args.subject,
                html=html,
                html_dir=html_path.parent,
            )
            if args.dry_run:
                print(
                    f"[DRY RUN] {idx}/{len(recipients)} real_to={real_to} effective_to={effective_to} "
                    f"inline_images={len(inline_images)}"
                )
                continue
            assert creds is not None
            try:
                result = gmail_api_send_message(access_token=creds.token, raw_message_bytes=msg.as_bytes())
                sent += 1
                print(
                    f"[SENT] {idx}/{len(recipients)} real_to={real_to} effective_to={effective_to} "
                    f"message_id={result.get('id')} inline_images={len(inline_images)}"
                )
            except Exception as exc:
                failed.append(real_to)
                print(f"[ERROR] {idx}/{len(recipients)} real_to={real_to} effective_to={effective_to}: {exc}")
                if args.stop_on_error:
                    break
    if args.dry_run:
        if args.single_message:
            print("[DRY RUN] Completed validation for 1 multi-recipient message.")
        else:
            print(f"[DRY RUN] Completed validation for {len(recipients)} recipient(s).")
        return 0
    if failed:
        if args.single_message:
            print(f"Sent {sent}/1 message(s). Failed: {len(failed)}")
        else:
            print(f"Sent {sent}/{len(recipients)} message(s). Failed: {len(failed)}")
        return 2
    if args.single_message:
        print("Sent 1/1 message(s).")
    else:
        print(f"Sent {sent}/{len(recipients)} message(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

