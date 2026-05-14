from __future__ import annotations

from origenlab_email_pipeline.canonical_gmail_dedupe import (
    EmailRowForDedupe,
    delete_ids_for_groups,
    folder_priority_rank,
    group_rows_by_normalized_mid,
    pick_survivor_row,
)


def _row(
    id_: int,
    *,
    folder: str | None,
    mid: str = "<x@y>",
    ac: int = 0,
    blen: int = 1,
) -> EmailRowForDedupe:
    return EmailRowForDedupe(
        id=id_,
        message_id=mid,
        folder=folder,
        source_file="gmail:contacto@origenlab.cl/INBOX",
        attachment_count=ac,
        body_len=blen,
        full_body_len=0,
        top_reply_len=0,
        body_text_clean_len=0,
    )


def test_folder_priority_sent_before_inbox() -> None:
    assert folder_priority_rank("[Gmail]/Enviados") < folder_priority_rank("INBOX")


def test_pick_survivor_prefers_sent_when_both_present() -> None:
    rows = [_row(10, folder="INBOX"), _row(20, folder="[Gmail]/Enviados")]
    assert pick_survivor_row(rows).id == 20


def test_pick_survivor_tie_goes_to_lower_id() -> None:
    rows = [
        _row(5, folder="[Gmail]/Enviados", blen=10),
        _row(3, folder="[Gmail]/Enviados", blen=10),
    ]
    assert pick_survivor_row(rows).id == 3


def test_pick_survivor_prefers_higher_attachment_count() -> None:
    rows = [
        _row(1, folder="[Gmail]/Enviados", ac=1, blen=5),
        _row(2, folder="[Gmail]/Enviados", ac=3, blen=5),
    ]
    assert pick_survivor_row(rows).id == 2


def test_delete_ids_only_dup_groups() -> None:
    g = group_rows_by_normalized_mid(
        [
            _row(1, folder="[Gmail]/Enviados"),
            _row(2, folder="[Gmail]/Enviados"),
            _row(99, folder="INBOX", mid="<other@z>"),
        ]
    )
    assert sorted(delete_ids_for_groups(g)) == [2]
