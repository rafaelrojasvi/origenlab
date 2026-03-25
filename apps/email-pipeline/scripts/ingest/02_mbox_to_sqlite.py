#!/usr/bin/env python3
"""Mbox → SQLite. Paths from .env / ORIGENLAB_* (see .env.example)."""
from __future__ import annotations

from collections import Counter, defaultdict
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    # scripts/ingest/02_mbox_to_sqlite.py -> apps/email-pipeline
    return Path(__file__).resolve().parents[2]


_ROOT = _repo_root()
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import (
    connect,
    init_schema,
    insert_attachment,
    insert_email,
)
from origenlab_email_pipeline.parse_mbox import (
    body_content,
    date_iso_from_msg,
    extract_body_structured,
    extract_full_and_top_reply,
    open_mbox,
    recipients_header,
    walk_attachments,
)
from tqdm import tqdm


def is_probably_mbox(path: Path) -> bool:
    if not path.is_file():
        return False
    # readpst often names mbox files without extension or as mbox
    if path.suffix.lower() in (".mbox", ""):
        return True
    try:
        with path.open("rb") as f:
            head = f.read(512)
        return head.startswith(b"From ") or b"From " in head[:200]
    except OSError:
        return False


def _max_error_ratio_from_env() -> float | None:
    raw = os.getenv("ORIGENLAB_INGEST_MAX_ERROR_RATIO", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        print(
            "Invalid ORIGENLAB_INGEST_MAX_ERROR_RATIO; expected float in [0, 1]. Ignoring.",
            file=sys.stderr,
        )
        return None
    if value < 0 or value > 1:
        print(
            "Invalid ORIGENLAB_INGEST_MAX_ERROR_RATIO; expected float in [0, 1]. Ignoring.",
            file=sys.stderr,
        )
        return None
    return value


def _fmt_error_counts(counter: Counter[str], *, top_n: int = 5) -> str:
    if not counter:
        return "(none)"
    return ", ".join(f"{name}={count}" for name, count in counter.most_common(top_n))


def main() -> None:
    settings = load_settings()
    mbox_root = settings.resolved_mbox_dir()
    db_path = settings.resolved_sqlite_path()

    if not mbox_root.is_dir():
        print(f"Mbox directory missing: {mbox_root}", file=sys.stderr)
        sys.exit(1)

    files = [p for p in mbox_root.rglob("*") if p.is_file() and is_probably_mbox(p)]
    if not files:
        print(f"No mbox-like files under: {mbox_root}", file=sys.stderr)
        sys.exit(1)

    conn = connect(db_path)
    init_schema(conn)
    conn.execute("DELETE FROM emails")
    conn.commit()
    total_inserted = 0
    total_messages = 0
    total_attachments = 0
    message_errors = 0
    attachment_errors = 0
    per_file_message_errors: dict[str, int] = defaultdict(int)
    per_file_attachment_errors: dict[str, int] = defaultdict(int)
    message_error_types: Counter[str] = Counter()
    attachment_error_types: Counter[str] = Counter()

    for mbox_path in tqdm(files, desc="mbox files"):
        mbox = open_mbox(str(mbox_path))
        if mbox is None:
            continue
        try:
            for msg in mbox:
                total_messages += 1
                try:
                    body, body_html = body_content(msg)
                    structured = extract_body_structured(msg)
                    full_body_clean, top_reply_clean = extract_full_and_top_reply(structured)
                    attachments = walk_attachments(msg)
                    email_id = insert_email(
                        conn,
                        source_file=str(mbox_path),
                        folder=str(mbox_path.parent),
                        message_id=msg.get("Message-ID"),
                        subject=msg.get("Subject"),
                        sender=msg.get("From"),
                        recipients=recipients_header(msg),
                        date_raw=msg.get("Date"),
                        date_iso=date_iso_from_msg(msg),
                        body=body,
                        body_html=body_html,
                        body_text_raw=structured["body_text_raw"],
                        body_text_clean=structured["body_text_clean"],
                        body_source_type=structured["body_source_type"],
                        body_has_plain=structured["body_has_plain"],
                        body_has_html=structured["body_has_html"],
                        full_body_clean=full_body_clean,
                        top_reply_clean=top_reply_clean,
                        attachment_count=len(attachments),
                        has_attachments=bool(attachments),
                    )
                    for att in attachments:
                        total_attachments += 1
                        try:
                            insert_attachment(
                                conn,
                                email_id=email_id,
                                part_index=att["part_index"],
                                filename=att["filename"],
                                content_type=att["content_type"],
                                content_disposition=att["content_disposition"],
                                size_bytes=att["size_bytes"],
                                content_id=att["content_id"],
                                is_inline=att["is_inline"],
                                sha256=att["sha256"],
                                saved_path=att["saved_path"],
                                created_at=None,
                            )
                        except Exception as exc:
                            attachment_errors += 1
                            per_file_attachment_errors[str(mbox_path)] += 1
                            attachment_error_types[type(exc).__name__] += 1
                            continue
                    total_inserted += 1
                except Exception as exc:
                    message_errors += 1
                    per_file_message_errors[str(mbox_path)] += 1
                    message_error_types[type(exc).__name__] += 1
                    continue
            conn.commit()
        finally:
            mbox.close()

    conn.close()
    print(f"SQLite: {db_path}  rows: {total_inserted}")
    print(
        "Ingest summary: "
        f"messages_seen={total_messages} inserted={total_inserted} "
        f"message_errors={message_errors} attachment_errors={attachment_errors}"
    )
    if message_errors > 0:
        print("Top message error types:", _fmt_error_counts(message_error_types))
        top_files = sorted(per_file_message_errors.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print(
            "Top files by message errors:",
            ", ".join(f"{Path(p).name}={c}" for p, c in top_files),
        )
    if attachment_errors > 0:
        print("Top attachment error types:", _fmt_error_counts(attachment_error_types))
        top_files = sorted(per_file_attachment_errors.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print(
            "Top files by attachment errors:",
            ", ".join(f"{Path(p).name}={c}" for p, c in top_files),
        )

    max_error_ratio = _max_error_ratio_from_env()
    if max_error_ratio is not None and total_messages > 0:
        error_ratio = message_errors / total_messages
        print(
            f"Message error ratio: {error_ratio:.4f} (threshold={max_error_ratio:.4f})"
        )
        if error_ratio > max_error_ratio:
            print(
                "Ingest failed quality threshold: "
                f"message_error_ratio={error_ratio:.4f} > {max_error_ratio:.4f}",
                file=sys.stderr,
            )
            sys.exit(2)


if __name__ == "__main__":
    main()
