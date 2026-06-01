"""Registry for manual prospect outreach + Cyber BCC extra (2026-06-01). Read-only facts for digest/audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ManualProspectKind = Literal["delivered_expected", "bounced_expected", "active_case", "cyber_bcc"]

FailureType = Literal[
    "no_such_user",
    "domain_not_found",
    "group_or_permission",
    "remote_server_misconfigured",
    "unknown",
]


@dataclass(frozen=True)
class ManualOutreachRow:
    email: str
    organization: str
    subject: str
    kind: ManualProspectKind
    expected_status: str
    expected_failure_type: FailureType | None = None
    notes: str = ""


MANUAL_PROSPECT_ROWS: tuple[ManualOutreachRow, ...] = (
    ManualOutreachRow(
        "giba@udec.cl",
        "Centro EULA-Chile UdeC",
        "Equipos para laboratorio y control de calidad ambiental — OrigenLab",
        "delivered_expected",
        "sent/manual_prospect_outreach",
    ),
    ManualOutreachRow(
        "kpena@cslab.cl",
        "CSLAB",
        "Equipos para laboratorio y control de calidad — CSLAB",
        "delivered_expected",
        "sent/manual_prospect_outreach",
    ),
    ManualOutreachRow(
        "pamela.munoz@uach.cl",
        "Laboratorio de Parasitología Veterinaria UACh",
        "Equipos para laboratorio veterinario y preparación de muestras — OrigenLa",
        "delivered_expected",
        "sent/manual_prospect_outreach",
    ),
    ManualOutreachRow(
        "hannelore.valentin@sgs.com",
        "SGS Chile",
        "Equipos para laboratorio y control de calidad — OrigenLab",
        "bounced_expected",
        "sent/bounced/suppressed",
        "no_such_user",
        "NDR postmaster@sgs.onmicrosoft.com — recipient not found at sgs.com",
    ),
    ManualOutreachRow(
        "ambiental@silobchile.cl",
        "Silob Chile",
        "Equipos para laboratorio ambiental y control de calidad — OrigenLab",
        "delivered_expected",
        "sent/manual_prospect_outreach",
    ),
    ManualOutreachRow(
        "udt@udt.cl",
        "Unidad de Desarrollo Tecnológico UdeC",
        "Equipos para preparación de muestras y laboratorio — UDT",
        "delivered_expected",
        "sent/manual_prospect_outreach",
    ),
    ManualOutreachRow(
        "mfbarrar@ug.uchile.cl",
        "Laboratorio de Toxinas Marinas UChile Castro",
        "Equipos para laboratorio de toxinas marinas y preparación de muestras — OrigenLab",
        "bounced_expected",
        "sent/bounced/suppressed",
        "no_such_user",
        "550 5.1.1",
    ),
    ManualOutreachRow(
        "jmieville@wss.cl",
        "World Survey Services",
        "Equipos para laboratorio, muestreo y control de calidad — OrigenLab",
        "bounced_expected",
        "sent/bounced/suppressed",
        "no_such_user",
    ),
    ManualOutreachRow(
        "ccorporativas@hcuch.cl",
        "Hospital Clínico Universidad de Chile",
        "Equipos para laboratorio clínico y apoyo pre-analítico — OrigenLab",
        "bounced_expected",
        "sent/bounced/suppressed or blocked",
        "group_or_permission",
    ),
)

ACTIVE_CASE_ROWS: tuple[ManualOutreachRow, ...] = (
    ManualOutreachRow(
        "marcos.a@hielscher.com",
        "Hielscher / UNACH",
        "Re: INTERNO [RCH-Universidad Adventista de Chile] Hielscher Ultrasonics...",
        "active_case",
        "supplier_followup/waiting_supplier",
        notes="Not marketing prospect",
    ),
    ManualOutreachRow(
        "juan-pablo.garcia@bureauveritas.com",
        "CESMEC / Bureau Veritas",
        "Re: Equipos para laboratorio de calibración y control de calidad — CESMEC",
        "active_case",
        "client_opportunity/catalogue_sent/waiting_client",
        notes="Catalogue PDF attached; not Cyber campaign",
    ),
)

CYBER_BCC_SUBJECT = (
    "CYBERDAY OrigenLab — equipos de laboratorio seleccionados hasta el 7 de junio"
)
CYBER_BCC_TO = "mle@mlelab.cl"
CYBER_BCC_RECIPIENTS: tuple[str, ...] = (
    "mle@mlelab.cl",
    "laboratorio@condecal.cl",
    "monica.cisternas@dukay.cl",
    "catalina.vera@ibbeta.cl",
    "contacto@lacofar.cl",
    "pcanales@mrlab.cl",
    "mlortiz@difrecalcine.cl",
    "asegcalidad@coesam.cl",
    "secretaria@colorbel.cl",
    "omeneses@cosmeticanacional.cl",
    "dfuente@durandin.cl",
    "mchicago@aramalab.cl",
    "plizama@labomed.cl",
    "rdoria@maver.cl",
    "vmoyer@maver.cl",
    "gstorme@mintlab.cl",
    "edith.yanez@dragpharma.cl",
)

CYBER_BCC_BOUNCED_EXPECTED: frozenset[str] = frozenset(
    {
        "plizama@labomed.cl",
        "pcanales@mrlab.cl",
        "vmoyer@maver.cl",
        "mchicago@aramalab.cl",
        "omeneses@cosmeticanacional.cl",
        "catalina.vera@ibbeta.cl",
        "rdoria@maver.cl",
    }
)

AUTO_REPLY_EXPECTED: frozenset[str] = frozenset(
    {
        "contacto@lacofar.cl",
        "contacto@idiem.cl",
    }
)

OPERATOR_DATE = "2026-06-01"
REPORT_PREFIX = f"manual_outreach_{OPERATOR_DATE}"
