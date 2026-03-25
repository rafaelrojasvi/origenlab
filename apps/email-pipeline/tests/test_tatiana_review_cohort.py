from __future__ import annotations

from origenlab_email_pipeline.tatiana_review_cohort import (
    build_review_signals,
    cohort_export_dedup_key,
    compute_marketing_export_rank_meta,
    hybrid_thread_contamination,
    likely_outbound_to_external,
    quote_heavy_full_body,
    subject_looks_reply_or_forward,
)


def test_likely_outbound_to_external() -> None:
    voice = frozenset({"labdelivery.cl"})
    assert likely_outbound_to_external("Buyer <a@client.cl>", voice_domains=voice) is True
    assert likely_outbound_to_external("Office <x@labdelivery.cl>", voice_domains=voice) is False


def test_quote_heavy_full_body() -> None:
    full = "Hi\n" + "\n".join("> quoted " + str(i) for i in range(20))
    top = "Hi"
    heavy, ratio = quote_heavy_full_body(full, top)
    assert heavy or ratio > 0.3


def test_build_review_signals_scores_allows_high_for_clean_commercial() -> None:
    sig = build_review_signals(
        sender='"Tatiana Vivanco" <t@labdelivery.cl>',
        recipients="c@external.cl",
        subject="Re: Cotización equipos laboratorio",
        full_body_clean="Estimado Juan,\n\nAdjunto cotización solicitada.\n\nSaludos cordiales,\nTatiana",
        top_reply_clean="Estimado Juan,\n\nAdjunto cotización solicitada.\n\nSaludos cordiales,\nTatiana",
        hybrid_body="Estimado Juan,\n\nAdjunto cotización solicitada.\n\nSaludos cordiales,\nTatiana",
        allowlist=frozenset(),
        voice_domains=frozenset({"labdelivery.cl"}),
        trusted_mention_domains=frozenset({"labdelivery.cl", "origenlab.cl"}),
        include_tatiana_text_signals=True,
    )
    assert "voice_sender_domain" in sig.inclusion_reasons
    assert sig.score >= 55.0
    assert not any(x.startswith("spoof_") for x in sig.risk_flags)


def test_subject_looks_reply_or_forward_mime_encoded() -> None:
    assert subject_looks_reply_or_forward("=?utf-8?Q?RE:_Semillas_Pioneer?=")
    assert not subject_looks_reply_or_forward("Cotización equipos")


def test_marketing_rank_meta_demotes_transfer_email() -> None:
    body = """Estimada Victoria,

Le envío datos bancarios para transferencia:

Cuenta corriente Banco BBVA

comprobante de transferencia adjunto
"""
    m = compute_marketing_export_rank_meta(
        subject="RE: Factura",
        hybrid_body=body,
        risk_flags=(),
        commercial_subtype="",
        intent_quote=False,
        intent_invoice=True,
        recipients="a@cliente.cl",
        voice_domains=frozenset({"labdelivery.cl"}),
    )
    assert m.rank_delta < -5.0
    assert m.ops_noise_hits >= 2


def test_marketing_rank_meta_boosts_fresh_cotizacion() -> None:
    body = """Estimado Juan,

Gracias por contactarnos.

Junto con saludar adjunto cotización por equipos.

Saludos,
"""
    m = compute_marketing_export_rank_meta(
        subject="Cotización laboratorio",
        hybrid_body=body,
        risk_flags=(),
        commercial_subtype="quote",
        intent_quote=True,
        intent_invoice=False,
        recipients="buyer@externo.cl",
        voice_domains=frozenset({"labdelivery.cl"}),
    )
    assert m.rank_delta > 5.0
    assert not m.subject_threaded
    assert m.export_tier >= 4


def test_cohort_export_dedup_key_stable_for_equivalent_rows() -> None:
    body = "Hola\n\nMismo texto."
    subj = "RE: Test"
    day = "2017-04-24T17:09:45+00:00"
    k1 = cohort_export_dedup_key(body, subj, day)
    k2 = cohort_export_dedup_key("  hola   \n\nmismo texto.  ", "re: test", day)
    assert k1 == k2


def test_hybrid_thread_contamination_flags_forward_open() -> None:
    hybrid = "De: Tatiana <t@example.com>\nEnviado el: jueves\nPara: x@y.cl\n\nHola"
    flags, pen = hybrid_thread_contamination(hybrid)
    assert "hybrid_opens_forward_header" in flags
    assert pen >= 9.0


def test_internal_downranked_without_outbound() -> None:
    base_kw = dict(
        sender="contacto@labdelivery.cl",
        subject="RE: interno",
        full_body_clean="Nota interna para equipo.\n\nSaludos,\nTatiana",
        top_reply_clean="Nota interna para equipo.\n\nSaludos,\nTatiana",
        hybrid_body="Nota interna para equipo.\n\nSaludos,\nTatiana",
        allowlist=frozenset(),
        voice_domains=frozenset({"labdelivery.cl"}),
        trusted_mention_domains=frozenset({"labdelivery.cl"}),
        include_tatiana_text_signals=False,
    )
    internal_only = build_review_signals(
        recipients="colleague@labdelivery.cl",
        **base_kw,
    )
    external_cc = build_review_signals(
        recipients="colleague@labdelivery.cl, buyer@cliente.cl",
        **base_kw,
    )
    assert internal_only.intent_primary == "internal"
    assert external_cc.likely_outbound_to_external is True
    assert internal_only.score < external_cc.score


def test_build_review_signals_lowers_on_spoof_pattern() -> None:
    sig = build_review_signals(
        sender="contacto@labdelivery.cl",
        recipients="x@y.com",
        subject="pedido en su espera - Chilexpress FAKE",
        full_body_clean="Si no está viendo haga clic aquí http://evil.test",
        top_reply_clean="Si no está viendo haga clic aquí http://evil.test",
        hybrid_body="Si no está viendo haga clic aquí http://evil.test",
        allowlist=frozenset(),
        voice_domains=frozenset({"labdelivery.cl"}),
        trusted_mention_domains=frozenset({"labdelivery.cl"}),
        include_tatiana_text_signals=False,
    )
    assert any("spoof_" in f for f in sig.risk_flags)
    assert sig.score < 40.0
