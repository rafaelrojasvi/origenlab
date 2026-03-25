"""Tests for Tatiana voice cohort allowlist and hybrid_style_body."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.db import connect, init_schema, insert_email
import origenlab_email_pipeline.tatiana_voice_cohort as tvc

from origenlab_email_pipeline.tatiana_voice_cohort import (
    hybrid_style_body,
    is_shared_mailbox_sender,
    is_voice_candidate_row,
    load_tatiana_allowlist,
    load_voice_sender_domains,
    sender_domain_matches_voice_domains,
    sender_header_matches_allowlist,
    subject_is_reply_or_forward,
    text_blob_mentions_tatiana_identity,
    trusted_domains_for_identity_mentions,
)


def test_hybrid_equal_returns_full() -> None:
    body = "Hola\n\nTexto\n\nSaludos cordiales"
    assert hybrid_style_body(body, body) == body


def test_hybrid_large_tail_prefers_top() -> None:
    top = "Gracias por su consulta."
    full = top + "\n\nOn Mon, 1 Jan wrote:\n> Old thread " + ("x" * 500)
    assert hybrid_style_body(full, top) == top


def test_hybrid_small_tail_prefers_full_for_closings() -> None:
    top = "Estimada,\n\nAdjunto cotización."
    full = top + "\n\nSaludos cordiales,\nTatiana"
    assert hybrid_style_body(full, top) == full


def test_hybrid_empty_branches() -> None:
    assert hybrid_style_body("", "only top") == "only top"
    assert hybrid_style_body("only full", "") == "only full"


def test_sender_header_matches_allowlist() -> None:
    allow = frozenset({"a@origenlab.cl"})
    assert sender_header_matches_allowlist('"Tatiana" <a@origenlab.cl>', allow)
    assert not sender_header_matches_allowlist("b@other.com", allow)


def test_shared_mailbox_detection() -> None:
    assert is_shared_mailbox_sender("Contacto <contacto@origenlab.cl>")
    assert not is_shared_mailbox_sender("T <t@origenlab.cl>")


def test_tracked_default_voice_domains_include_labdelivery() -> None:
    assert "labdelivery.cl" in load_voice_sender_domains()


def test_sender_domain_matches_labdelivery() -> None:
    doms = frozenset({"labdelivery.cl"})
    assert sender_domain_matches_voice_domains('"T" <a@labdelivery.cl>', doms)
    assert sender_domain_matches_voice_domains("b@mail.labdelivery.cl", doms)
    assert not sender_domain_matches_voice_domains("c@origenlab.cl", doms)


def test_text_blob_mentions_whole_word_only() -> None:
    assert text_blob_mentions_tatiana_identity("Hola Tatiana,", "x")
    assert text_blob_mentions_tatiana_identity(None, "Apellido Vivanco")
    assert not text_blob_mentions_tatiana_identity("xtatianax", None)


def test_voice_candidate_tatiana_text_signal_origenlab() -> None:
    doms = load_voice_sender_domains()
    trusted = trusted_domains_for_identity_mentions(doms)
    assert is_voice_candidate_row(
        '"Equipo" <ops@origenlab.cl>',
        frozenset(),
        voice_domains=frozenset(),
        full_body_clean="Gracias.\n\nTatiana",
        top_reply_clean="Gracias.\n\nTatiana",
        include_tatiana_text_signals=True,
        trusted_domains_for_text_signals=trusted,
    )


def test_voice_candidate_text_signal_blocked_for_shared_mailbox() -> None:
    trusted = trusted_domains_for_identity_mentions(frozenset())
    assert not is_voice_candidate_row(
        '"C" <contacto@origenlab.cl>',
        frozenset(),
        voice_domains=frozenset(),
        full_body_clean="Saludos\nTatiana",
        top_reply_clean="Saludos\nTatiana",
        include_tatiana_text_signals=True,
        trusted_domains_for_text_signals=trusted,
    )


def test_voice_candidate_text_signal_rejects_external_sender() -> None:
    trusted = trusted_domains_for_identity_mentions(frozenset())
    assert not is_voice_candidate_row(
        '"Client" <c@gmail.com>',
        frozenset(),
        voice_domains=frozenset(),
        full_body_clean="Hola Tatiana\n\nGracias",
        top_reply_clean="Hola Tatiana\n\nGracias",
        include_tatiana_text_signals=True,
        trusted_domains_for_text_signals=trusted,
    )


def test_voice_candidate_by_domain_without_allowlist() -> None:
    doms = frozenset({"labdelivery.cl"})
    assert is_voice_candidate_row(
        '"Tatiana" <ventas@labdelivery.cl>',
        frozenset(),
        voice_domains=doms,
    )


def test_voice_candidate_respects_shared_policy() -> None:
    allow = frozenset({"contacto@origenlab.cl"})
    hdr = "x <contacto@origenlab.cl>"
    assert not is_voice_candidate_row(hdr, allow, allow_shared_mailboxes=False)
    assert is_voice_candidate_row(hdr, allow, allow_shared_mailboxes=True)


def test_subject_reply_forward() -> None:
    assert subject_is_reply_or_forward("Re: cotización")
    assert subject_is_reply_or_forward("FW: pedido")
    assert not subject_is_reply_or_forward("Cotización equipos")


def test_load_allowlist_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ORIGENLAB_TATIANA_SENDERS", raising=False)
    monkeypatch.delenv("ORIGENLAB_TATIANA_SENDERS_FILE", raising=False)
    assert load_tatiana_allowlist() == frozenset()

    monkeypatch.setenv("ORIGENLAB_TATIANA_SENDERS", " One@x.com , two@y.com ")
    assert load_tatiana_allowlist() == frozenset({"one@x.com", "two@y.com"})

    p = tmp_path / "s.txt"
    p.write_text("# c\n\n  THREE@z.com  \n", encoding="utf-8")
    monkeypatch.setenv("ORIGENLAB_TATIANA_SENDERS_FILE", str(p))
    monkeypatch.setenv("ORIGENLAB_TATIANA_SENDERS", "one@x.com")
    assert load_tatiana_allowlist() == frozenset({"one@x.com", "three@z.com"})


def test_load_allowlist_from_default_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p = tmp_path / "tatiana_senders.local.txt"
    p.write_text("# x\n  default@local.test  \n", encoding="utf-8")
    monkeypatch.delenv("ORIGENLAB_TATIANA_SENDERS", raising=False)
    monkeypatch.delenv("ORIGENLAB_TATIANA_SENDERS_FILE", raising=False)
    monkeypatch.setattr(tvc, "default_allowlist_path", lambda: p)
    assert load_tatiana_allowlist() == frozenset({"default@local.test"})


def _load_dataset_script(name: str, relative: str):
    repo = Path(__file__).resolve().parents[1]
    path = repo / "scripts" / "dataset" / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[call-arg]
    return mod


def test_report_tatiana_cohort_metrics_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "e.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    insert_email(
        conn,
        source_file="f.mbox",
        folder="/mbox/Sent",
        message_id="<mid1>",
        subject="Cotización",
        sender='"Tatiana" <writer@test.com>',
        recipients="c@client.cl",
        date_raw="",
        date_iso="2024-06-01T12:00:00",
        body="",
        full_body_clean="Estimada,\n\nAdjunto documentos.\n\nSaludos",
        top_reply_clean="Estimada,\n\nAdjunto documentos.",
    )
    insert_email(
        conn,
        source_file="f.mbox",
        folder="/mbox/Inbox",
        message_id="<mid2>",
        subject="Re: pedido",
        sender='"Tatiana" <writer@test.com>',
        recipients="x@y.com",
        date_raw="",
        date_iso="2023-01-01T00:00:00",
        body="",
        full_body_clean="Ok",
        top_reply_clean="Ok",
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORIGENLAB_TATIANA_SENDERS", "writer@test.com")
    monkeypatch.delenv("ORIGENLAB_TATIANA_SENDERS_FILE", raising=False)

    class _S:
        def resolved_sqlite_path(self) -> Path:
            return db_path

        def resolved_reports_dir(self) -> Path:
            return tmp_path / "reports"

    mod = _load_dataset_script("rep_tat_metrics", "report_tatiana_cohort_metrics.py")
    monkeypatch.setattr(mod, "load_settings", lambda: _S(), raising=False)
    monkeypatch.setattr(sys, "argv", ["report_tatiana_cohort_metrics.py"], raising=False)
    mod.main()
    out = capsys.readouterr().out
    assert "Cohort (domain and/or allowlist, shared-mailbox policy): 2" in out
    assert "2024" in out and "2023" in out


def test_export_tatiana_review_sample_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "e2.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    long_body = "Para cotizar.\n\n" + ("x" * 500)
    insert_email(
        conn,
        source_file="f.mbox",
        folder="/mbox/Sent",
        message_id="<m1>",
        subject="Fwd: oferta",
        sender='"T" <writer@test.com>',
        recipients="a@b.com",
        date_raw="",
        date_iso="2024-01-01T00:00:00",
        body="",
        full_body_clean=long_body,
        top_reply_clean=long_body,
    )
    conn.commit()
    conn.close()

    out_csv = tmp_path / "review.csv"
    monkeypatch.setenv("ORIGENLAB_TATIANA_SENDERS", "writer@test.com")

    class _S:
        def resolved_sqlite_path(self) -> Path:
            return db_path

        def resolved_reports_dir(self) -> Path:
            return tmp_path / "reports"

    mod = _load_dataset_script("exp_tat_review", "export_tatiana_review_sample.py")
    monkeypatch.setattr(mod, "load_settings", lambda: _S(), raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_tatiana_review_sample.py",
            "--per-bucket",
            "1",
            "--seed",
            "1",
            "-o",
            str(out_csv),
        ],
        raising=False,
    )
    mod.main()
    text = out_csv.read_text(encoding="utf-8")
    assert "label_author_confidence" in text
    assert "writer@test.com" in text
    assert "hybrid_style_body_preview" in text
