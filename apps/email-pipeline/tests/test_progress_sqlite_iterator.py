"""Batched SQLite scan with tqdm (email table count)."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.progress import iter_sqlite_email_batches_with_progress


def test_iter_sqlite_email_batches_yields_all_rows() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE emails (id INTEGER)")
    for i in range(5):
        conn.execute("INSERT INTO emails VALUES (?)", (i,))
    conn.commit()
    cur = conn.execute("SELECT id FROM emails ORDER BY id")
    batches = list(
        iter_sqlite_email_batches_with_progress(conn, cur, desc="test", batch_size=2)
    )
    assert sum(len(b) for b in batches) == 5
    assert [row[0] for batch in batches for row in batch] == [0, 1, 2, 3, 4]
