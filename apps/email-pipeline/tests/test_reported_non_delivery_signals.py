from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery


def test_positive_spanish_no_me_llego() -> None:
    assert text_suggests_reported_non_delivery("Re: Cotización", "Hola, no me llegó el correo con la cotización") is True


def test_positive_english_never_got() -> None:
    assert text_suggests_reported_non_delivery(None, "I never got your email about the quote.") is True


def test_negative_no_recibi_respuesta() -> None:
    assert text_suggests_reported_non_delivery("Seguimiento", "Aún no recibí respuesta de su equipo.") is False


def test_negative_empty() -> None:
    assert text_suggests_reported_non_delivery(None, None) is False
