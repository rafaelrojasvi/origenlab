from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_ingest_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "ingest" / "02_mbox_to_sqlite.py"
    spec = importlib.util.spec_from_file_location("ingest_02_mbox_to_sqlite", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def test_ingest_counts_and_prints_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_ingest_module()

    mbox_root = tmp_path / "mbox"
    mbox_root.mkdir(parents=True)
    mbox_file = mbox_root / "sample.mbox"
    mbox_file.write_bytes(b"From test\n")
    db_path = tmp_path / "sqlite" / "emails.sqlite"

    class DummySettings:
        def resolved_mbox_dir(self) -> Path:
            return mbox_root

        def resolved_sqlite_path(self) -> Path:
            return db_path

    class DummyConn:
        def execute(self, *_args, **_kwargs):
            return self

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    class DummyMbox:
        def __iter__(self):
            class DummyMsg:
                def get(self, _key: str):
                    return None

            return iter([DummyMsg(), DummyMsg()])

        def close(self) -> None:
            return None

    calls = {"body": 0, "insert_attachment": 0}

    def fake_body_content(_msg):
        calls["body"] += 1
        if calls["body"] == 1:
            raise ValueError("broken message payload")
        return ("ok body", "")

    def fake_insert_attachment(*_args, **_kwargs):
        calls["insert_attachment"] += 1
        raise RuntimeError("attachment insert failed")

    monkeypatch.setattr(mod, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(mod, "connect", lambda _path: DummyConn())
    monkeypatch.setattr(mod, "init_schema", lambda _conn: None)
    monkeypatch.setattr(mod, "open_mbox", lambda _path: DummyMbox())
    monkeypatch.setattr(mod, "body_content", fake_body_content)
    monkeypatch.setattr(
        mod,
        "extract_body_structured",
        lambda _msg: {
            "body_text_raw": "r",
            "body_text_clean": "c",
            "body_source_type": "plain",
            "body_has_plain": True,
            "body_has_html": False,
        },
    )
    monkeypatch.setattr(mod, "extract_full_and_top_reply", lambda _s: ("full", "top"))
    monkeypatch.setattr(
        mod,
        "walk_attachments",
        lambda _msg: [
            {
                "part_index": 0,
                "filename": "a.pdf",
                "content_type": "application/pdf",
                "content_disposition": "attachment",
                "size_bytes": 10,
                "content_id": None,
                "is_inline": False,
                "sha256": "x",
                "saved_path": None,
            }
        ],
    )
    monkeypatch.setattr(mod, "insert_email", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(mod, "insert_attachment", fake_insert_attachment)

    mod.main()
    out = capsys.readouterr().out
    assert "Ingest summary:" in out
    assert "message_errors=1" in out
    assert "attachment_errors=1" in out
    assert "ValueError=1" in out
    assert "RuntimeError=1" in out


def _ingest_mod_for_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    num_messages: int,
    fail_message_indices: set[int],
):
    mod = _load_ingest_module()

    mbox_root = tmp_path / "mbox"
    mbox_root.mkdir(parents=True)
    (mbox_root / "sample.mbox").write_bytes(b"From test\n")
    db_path = tmp_path / "sqlite" / "emails.sqlite"

    class DummySettings:
        def resolved_mbox_dir(self) -> Path:
            return mbox_root

        def resolved_sqlite_path(self) -> Path:
            return db_path

    class DummyConn:
        def execute(self, *_args, **_kwargs):
            return self

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    class DummyMsg:
        def get(self, _key: str):
            return None

    class DummyMbox:
        def __iter__(self):
            return iter([DummyMsg() for _ in range(num_messages)])

        def close(self) -> None:
            return None

    idx = {"n": 0}

    def fake_body_content(_msg):
        i = idx["n"]
        idx["n"] += 1
        if i in fail_message_indices:
            raise ValueError("broken")
        return ("ok", "")

    monkeypatch.setattr(mod, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(mod, "connect", lambda _path: DummyConn())
    monkeypatch.setattr(mod, "init_schema", lambda _conn: None)
    monkeypatch.setattr(mod, "open_mbox", lambda _path: DummyMbox())
    monkeypatch.setattr(mod, "body_content", fake_body_content)
    monkeypatch.setattr(
        mod,
        "extract_body_structured",
        lambda _msg: {
            "body_text_raw": "r",
            "body_text_clean": "c",
            "body_source_type": "plain",
            "body_has_plain": True,
            "body_has_html": False,
        },
    )
    monkeypatch.setattr(mod, "extract_full_and_top_reply", lambda _s: ("full", "top"))
    monkeypatch.setattr(mod, "walk_attachments", lambda _msg: [])
    monkeypatch.setattr(mod, "insert_email", lambda *_a, **_k: 1)
    monkeypatch.setattr(mod, "insert_attachment", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "tqdm", lambda iterable, **_k: iterable)
    return mod


def test_ingest_threshold_exceeded_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORIGENLAB_INGEST_MAX_ERROR_RATIO", "0.2")
    mod = _ingest_mod_for_threshold(
        monkeypatch,
        tmp_path,
        num_messages=5,
        fail_message_indices={0, 1, 2, 3, 4},
    )
    with pytest.raises(SystemExit) as excinfo:
        mod.main()
    assert excinfo.value.code == 2


def test_ingest_threshold_below_no_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ORIGENLAB_INGEST_MAX_ERROR_RATIO", "0.5")
    mod = _ingest_mod_for_threshold(
        monkeypatch,
        tmp_path,
        num_messages=10,
        fail_message_indices={0},
    )
    mod.main()
    out = capsys.readouterr().out
    assert "Message error ratio:" in out
    assert "threshold=0.5000" in out


def test_ingest_invalid_threshold_env_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ORIGENLAB_INGEST_MAX_ERROR_RATIO", "not-a-float")
    mod = _ingest_mod_for_threshold(
        monkeypatch,
        tmp_path,
        num_messages=4,
        fail_message_indices={0, 1, 2},
    )
    mod.main()
    err = capsys.readouterr().err
    assert "Invalid ORIGENLAB_INGEST_MAX_ERROR_RATIO" in err
