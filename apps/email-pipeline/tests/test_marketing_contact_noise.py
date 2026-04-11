from origenlab_email_pipeline.marketing_contact_noise import (
    marketing_outreach_noise_email,
    marketing_outreach_noise_organization_guess,
)


def test_newsletter_patterns() -> None:
    assert marketing_outreach_noise_email("newsletter@universidad.cl")
    assert marketing_outreach_noise_email("hello@newsletter.substack.com")
    assert marketing_outreach_noise_email("updates@convertkit.com")


def test_noise_domains_and_locals() -> None:
    assert marketing_outreach_noise_email("avisos@mercadopublico.cl")
    assert marketing_outreach_noise_email("cl.notificacion@dhl.com")
    assert marketing_outreach_noise_email("system@wherex.com")
    assert marketing_outreach_noise_email("c6@facebookmail.com")
    assert marketing_outreach_noise_email("info@twitter.com")
    assert marketing_outreach_noise_email("invitations@linkedin.com")
    assert marketing_outreach_noise_email("support@dhl.com")


def test_not_noise_typical_lab_contact() -> None:
    assert not marketing_outreach_noise_email("compras@hospital.cl")
    assert not marketing_outreach_noise_email("laboratorio@universidad.cl")


def test_noise_org_guess() -> None:
    assert marketing_outreach_noise_organization_guess("Mercadopublico")
    assert not marketing_outreach_noise_organization_guess("Hospital Regional")
