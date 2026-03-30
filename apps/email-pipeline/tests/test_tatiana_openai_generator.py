from __future__ import annotations

import json

import pytest

from origenlab_email_pipeline.config import Settings
from origenlab_email_pipeline.tatiana_copilot.draft_package import build_draft_package
from origenlab_email_pipeline.tatiana_copilot.generator_factory import (
    TatianaLLMConfigurationError,
    resolve_draft_generator,
)
from origenlab_email_pipeline.tatiana_copilot.index import TatianaExampleIndex
from origenlab_email_pipeline.tatiana_copilot.openai_chat_generator import (
    OpenAIChatDraftGenerator,
    cotización_pointer_is_email_only,
    enrich_generic_asunto_line,
    filter_ungrounded_sentences,
    harden_asunto_line,
    maybe_bullet_split_product_line,
    normalize_signature_block,
    postprocess_openai_draft,
    remove_placeholder_model_bullets,
    sanitize_body_grounding,
    should_abstain_low_information_case,
)
from origenlab_email_pipeline.tatiana_copilot.schemas import DraftCase, ExampleRecord


def test_resolve_unknown_generator() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        resolve_draft_generator("not_a_generator")


def test_resolve_mock() -> None:
    g = resolve_draft_generator("mock")
    assert g.__class__.__name__ == "MockDraftGenerator"


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ORIGENLAB_TATIANA_OPENAI_API_KEY", raising=False)
    s = Settings()
    assert s.resolved_tatiana_openai_api_key() is None
    with pytest.raises(TatianaLLMConfigurationError, match="API key missing"):
        OpenAIChatDraftGenerator.from_settings(s)


def test_short_body_abstains() -> None:
    class _C:
        pass

    gen = OpenAIChatDraftGenerator(client=_C(), model="m", min_body_chars=20, abstain_on_empty_retrieval=False)
    r = gen.generate(
        {
            "case": {"body_text": "short", "subject": "s"},
            "style_examples": [{"example_id": "1"}],
            "retrieved_precedents": [],
        }
    )
    assert r.abstained is True
    assert "body_too_short" in r.notes
    assert r.provider_name == "openai_chat"


def test_empty_retrieval_abstains_when_enabled() -> None:
    class _C:
        pass

    gen = OpenAIChatDraftGenerator(
        client=_C(), model="m", min_body_chars=0, abstain_on_empty_retrieval=True
    )
    r = gen.generate(
        {
            "instruction": "x",
            "case": {"body_text": "y" * 50, "subject": "s"},
            "style_examples": [],
            "retrieved_precedents": [],
        }
    )
    assert r.abstained is True
    assert "insufficient_retrieval_evidence" in r.notes


def test_api_error_abstains_with_note() -> None:
    class _Completions:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("boom")

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    gen = OpenAIChatDraftGenerator(
        client=_Client(), model="m", min_body_chars=0, abstain_on_empty_retrieval=False
    )
    r = gen.generate(
        {
            "instruction": "i",
            "case": {"body_text": "y" * 50, "subject": "s"},
            "style_examples": [{"example_id": "a"}],
            "retrieved_precedents": [],
        }
    )
    assert r.abstained is True
    assert "openai_error:RuntimeError" in r.notes


def test_successful_completion_shape() -> None:
    class _Msg:
        content = "Asunto: Re: Demo\n\nEstimados,\n\nGracias por su consulta.\n"

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]

    class _Completions:
        @staticmethod
        def create(**kwargs):
            return _Completion()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    gen = OpenAIChatDraftGenerator(
        client=_Client(), model="m", min_body_chars=0, abstain_on_empty_retrieval=False
    )
    r = gen.generate(
        {
            "instruction": "draft",
            "case": {"body_text": "y" * 50, "subject": "s"},
            "style_examples": [{"example_id": "1"}],
            "retrieved_precedents": [{"example_id": "2"}],
        }
    )
    assert r.abstained is False
    assert "Asunto:" in r.text
    assert r.provider_name == "openai_chat"
    assert r.notes == "openai_chat_completion"


def test_model_abstain_token() -> None:
    class _Msg:
        content = "ABSTAIN"

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]

    class _Completions:
        @staticmethod
        def create(**kwargs):
            return _Completion()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    gen = OpenAIChatDraftGenerator(
        client=_Client(), model="m", min_body_chars=0, abstain_on_empty_retrieval=False
    )
    r = gen.generate(
        {
            "instruction": "draft",
            "case": {"body_text": "y" * 50, "subject": "s"},
            "style_examples": [{"example_id": "1"}],
            "retrieved_precedents": [],
        }
    )
    assert r.abstained is True
    assert r.notes == "model_abstained"


def test_cotización_pointer_is_email_only_detects_corrupted_body() -> None:
    body = (
        "Estimada María Adriana,\n\n"
        "Junto con saludar le adjunto cotización por\n"
        "mavalenzuela@example.com\n"
    )
    assert cotización_pointer_is_email_only(body) is True


def test_should_abstain_low_information_for_corrupted_cotización() -> None:
    body = (
        "Estimada María Adriana,\n\n"
        "Junto con saludar le adjunto cotización por\n"
        "mavalenzuela@example.com\n"
    )
    assert should_abstain_low_information_case(body) is True


def test_should_not_abstain_synthetic_repeat_body() -> None:
    assert should_abstain_low_information_case("y" * 50) is False


def test_enrich_generic_asunto_uses_case_context() -> None:
    case = (
        "Estimado Pedro,\n\n"
        "Adjunto cotización medidor de pH ST300 marca Ohaus con 15 días de entrega.\n"
    )
    draft = "Asunto: Cotización\n\nEstimado Pedro,\n\nGracias.\n"
    out = enrich_generic_asunto_line(draft, case)
    assert "ST300" in out.splitlines()[0] or "medidor" in out.splitlines()[0].lower()


def test_maybe_bullet_split_product_line_splits_dual_models() -> None:
    line = (
        "Le envío cotización del Densímetro Digital modelos DS7700 Krüss "
        "y Modelo SG-Ultra Max Eagle Eye."
    )
    got = maybe_bullet_split_product_line(line)
    assert got is not None
    assert got.startswith("- ")
    assert "\n- Modelo " in got


def test_normalize_signature_replaces_tail_from_saludos() -> None:
    draft = (
        "Cuerpo.\n\n"
        "Saludos cordiales,\n\n"
        "Tatiana Vivanco\n\n"
        "Celular: 999\n"
    )
    out = normalize_signature_block(draft)
    assert "+56-2-3410805" in out
    assert "Cuerpo." in out
    assert out.count("Saludos cordiales") == 1


def test_strip_brochure_halogen_pitch_when_case_has_no_corroboration() -> None:
    pitch = "En general, el halógeno es 40% más rápido y tiene mayor sensibilidad que el infrarrojo."
    case_polluted = (
        "Estimado Jan,\n\nJunto con saludar adjunto cotización N°6757-19.\n\n"
        f"{pitch}\n\nQuedo atenta."
    )
    out = filter_ungrounded_sentences(pitch, case_polluted)
    assert "40%" not in out
    assert "más rápido" not in out.lower()
    case_ficha = (
        "Cliente pregunta por termobalanza. Según ficha técnica Ohaus el halógeno es 40% más rápido "
        "y mayor sensibilidad vs infrarrojo."
    )
    out_ok = filter_ungrounded_sentences(pitch, case_ficha)
    assert "40%" in out_ok or "más rápido" in out_ok.lower()


def test_stock_pitch_allowed_when_customer_asks_comparison() -> None:
    pitch = "En general, el halógeno es más rápido y tiene mayor sensibilidad que el infrarrojo."
    case_q = "¿Cuál es más rápido, halógeno o infrarrojo? Cotice termobalanza."
    assert pitch.strip() in filter_ungrounded_sentences(pitch, case_q)


def test_strip_unsupported_comparative_when_not_in_case() -> None:
    para = "En general, el halógeno es 40% más rápido que el infrarrojo. Gracias."
    case = "Adjunto cotización termobalanza Ohaus sin comparativas."
    out = filter_ungrounded_sentences(para, case)
    assert "40%" not in out
    assert "más rápido" not in out.lower()
    case_ok = "En general el halógeno es 40% más rápido según ficha."
    out_ok = filter_ungrounded_sentences(para, case_ok)
    assert "40%" in out_ok


def test_strip_unsupported_quote_reference() -> None:
    sent = "Adjunto cotización N°6757-19 por equipos."
    case = "Solicitud de cotización de termobalanza."
    out = filter_ungrounded_sentences(sent, case)
    assert "6757" not in out


def test_remove_placeholder_model_lines() -> None:
    body = "Le cotizo alternativas:\n\n- Modelo 1\n- Modelo 2\n- Modelo 3\n\nSaludos."
    out = remove_placeholder_model_bullets(body)
    assert "Modelo 1" not in out
    assert "Modelo 2" not in out


def test_sanitize_body_removes_unsupported_install_commitment() -> None:
    raw = (
        "Hola.\n\n"
        "El plazo es de 3 a 4 semanas e incluye puesta en marcha e instalación.\n\n"
        "Saludos cordiales,\n\nX\n"
    )
    case = "Cotización digestor sin mencionar instalación ni plazo."
    # Below asunto split mimics postprocess: only main letter body
    low = raw.lower()
    idx = low.find("saludos cordiales")
    main = raw[:idx]
    cleaned = sanitize_body_grounding(main, case)
    assert "puesta en marcha" not in cleaned.lower()
    assert "instalación" not in cleaned.lower()


def test_harden_asunto_truncates_long_line() -> None:
    long_subj = "Cotización – " + "x" * 120
    draft = f"Asunto: {long_subj}\n\nCuerpo.\n"
    out = harden_asunto_line(draft)
    first = out.splitlines()[0]
    assert len(first) < len(draft.splitlines()[0])
    assert first.endswith("...") or len(first) <= 110


def test_enrich_weak_labdelivery_subject() -> None:
    case = "Cliente pide frascos de laboratorio para cotizar."
    draft = "Asunto: Cotización Labdelivery\n\nEstimado,\n\nGracias.\n"
    out = enrich_generic_asunto_line(draft, case)
    assert "frascos" in out.splitlines()[0].lower()


def test_postprocess_dedupes_repeated_closing() -> None:
    raw = (
        "Asunto: Re: X\n\n"
        "Hola.\n\n"
        "Quedo atenta a cualquier consulta.\n\n"
        "Quedo atenta a cualquier consulta.\n\n"
        "Saludos cordiales,\n\nX\n"
    )
    case = "Estimado Juan, cotización modelo ST100."
    out = postprocess_openai_draft(raw, case)
    assert out.lower().count("quedo atenta a cualquier consulta") == 1


def test_build_draft_package_with_openai_generator() -> None:
    ex_pool = ExampleRecord(
        example_id="e_pool",
        source_file="f",
        source_row_id="1",
        kind="retrieval",
        label="quote_followup",
        subject="Cotización balanza",
        body_text="Adjuntamos cotización por balanza analítica modelo XY-100 y especificaciones técnicas.",
        search_text="",
        date_iso=None,
        freshness_bucket=None,
        language_signal=None,
        contamination_signal=None,
        keep_for_style_guide=True,
        keep_for_retrieval_later=True,
        metadata={},
    )
    ex_hold = ExampleRecord(
        example_id="e_hold",
        source_file="f",
        source_row_id="2",
        kind="retrieval",
        label="quote_followup",
        subject="Cotización",
        body_text="Necesitamos cotización de balanza analítica para laboratorio.",
        search_text="",
        date_iso=None,
        freshness_bucket=None,
        language_signal=None,
        contamination_signal=None,
        keep_for_style_guide=True,
        keep_for_retrieval_later=True,
        metadata={},
    )
    idx = TatianaExampleIndex.build(
        style_examples=[ex_pool],
        retrieval_examples=[ex_pool, ex_hold],
        method="tfidf",
    )

    class _Msg:
        content = "Asunto: Re: Cotización\n\nEstimado cliente,\n\nEn respuesta a su solicitud...\n"

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]

    class _Completions:
        @staticmethod
        def create(**kwargs):
            return _Completion()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    gen = OpenAIChatDraftGenerator(
        client=_Client(), model="gpt-test", min_body_chars=10, abstain_on_empty_retrieval=False
    )
    case = DraftCase(
        case_id="c1",
        subject="Cotización balanza",
        body_text="Por favor envíenos cotización y plazo de entrega para balanza analítica.",
        expected_label="quote_followup",
        context_metadata={},
    )
    pkg = build_draft_package(case=case, index=idx, generator=gen, exclude_example_ids={"e_hold"})
    d = pkg.to_dict()
    assert d["provider_name"] == "openai_chat"
    assert d["abstained"] is False
    assert "Asunto:" in d["generated_draft"]
    assert "prompt_blocks" in d
    assert isinstance(d["prompt_blocks"], dict)
    assert json.dumps(d, ensure_ascii=True)

