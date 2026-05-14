"""Deterministic survivor selection for duplicate ``message_id`` within canonical Gmail rows.

Used by ``scripts/maintenance/dedupe_canonical_gmail_messages.py``. Does not touch legacy mbox paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source


def canonical_gmail_where_sql(table_alias: str | None = None) -> str:
    """SQL boolean fragment for canonical Workspace Gmail ``emails`` rows."""
    return sql_predicate_contacto_gmail_source(table_alias=table_alias, coalesce_null=False)


@dataclass(frozen=True, slots=True)
class EmailRowForDedupe:
    """Minimal row shape for survivor selection."""

    id: int
    message_id: str
    folder: str | None
    source_file: str | None
    attachment_count: int | None
    body_len: int
    full_body_len: int
    top_reply_len: int
    body_text_clean_len: int


def folder_priority_rank(folder: str | None) -> int:
    """Lower rank wins. Aligns with operator preference: Sent, Inbox, Drafts, Trash, else last."""
    f = (folder or "").strip().lower()
    if "enviados" in f or "sent mail" in f:
        return 0
    if f == "inbox" or "bandeja de entrada" in f:
        return 1
    if "borrador" in f or "draft" in f:
        return 2
    if "papelera" in f or "trash" in f or "bin" in f:
        return 3
    return 10


def body_completeness_score(row: EmailRowForDedupe) -> int:
    return (
        row.body_len
        + row.full_body_len
        + row.top_reply_len
        + row.body_text_clean_len
    )


def pick_survivor_row(rows: Sequence[EmailRowForDedupe]) -> EmailRowForDedupe:
    """Pick one survivor per ``message_id`` group using deterministic tie-breaks.

    Order:
    1. Best folder (Sent / Inbox / Drafts / Trash / other).
    2. Highest body-completeness proxy (sum of text field lengths).
    3. Highest ``attachment_count``.
    4. Lowest ``id`` (stable, typically earliest insert).
    """
    if not rows:
        raise ValueError("empty rows")
    if len(rows) == 1:
        return rows[0]

    def sort_key(r: EmailRowForDedupe) -> tuple[int, int, int, int]:
        ac = int(r.attachment_count or 0)
        return (
            folder_priority_rank(r.folder),
            -body_completeness_score(r),
            -ac,
            r.id,
        )

    return min(rows, key=sort_key)


def pick_survivor_ids(rows_by_mid: dict[str, list[EmailRowForDedupe]]) -> dict[str, int]:
    """Map normalized ``message_id`` -> survivor ``id`` for groups with len>=2."""
    out: dict[str, int] = {}
    for mid, lst in rows_by_mid.items():
        if len(lst) < 2:
            continue
        out[mid] = pick_survivor_row(lst).id
    return out


def delete_ids_for_groups(rows_by_mid: dict[str, list[EmailRowForDedupe]]) -> list[int]:
    """All email ``id``s that would be removed (non-survivors) for duplicate groups."""
    to_delete: list[int] = []
    for mid, lst in rows_by_mid.items():
        if len(lst) < 2:
            continue
        keep = pick_survivor_row(lst).id
        for r in lst:
            if r.id != keep:
                to_delete.append(r.id)
    return sorted(to_delete)


def group_rows_by_normalized_mid(rows: Iterable[EmailRowForDedupe]) -> dict[str, list[EmailRowForDedupe]]:
    groups: dict[str, list[EmailRowForDedupe]] = {}
    for r in rows:
        mid = (r.message_id or "").strip().lower()
        if not mid:
            continue
        groups.setdefault(mid, []).append(r)
    return groups
