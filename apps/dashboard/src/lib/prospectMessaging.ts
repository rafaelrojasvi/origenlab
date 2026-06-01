/** Operator-facing copy for Prospectos drawer (no API changes). */

import type {
  LeadProspectDetailResponseUi,
  LeadProspectDetailUi,
  LeadProspectRecommendationUi,
} from "../api/leadIntelTypes";
import { hasProspectEmail, prospectBuyerTypeLabel } from "./prospectLabels";

export interface PorQueImportaContent {
  queHaceEvidencia: string | null;
  necesidadProbable: string | null;
  porQueInteresante: string;
}

export interface MessagePreviewContent {
  kind: "net_new" | "same_domain_followup" | "gmail_draft" | "public_tender" | "none";
  title: string;
  subject?: string;
  body?: string;
  note?: string;
}

function firstProductTopic(productAngle: string | null | undefined): string {
  if (!productAngle?.trim()) return "equipos de laboratorio";
  const first = productAngle.split(";")[0]?.trim();
  return first || "equipos de laboratorio";
}

function sectorHint(sector: string | null | undefined, buyerType: string | null | undefined): string {
  const parts: string[] = [];
  if (sector?.trim()) parts.push(sector.trim());
  const buyer = prospectBuyerTypeLabel(buyerType);
  if (buyer !== "Sin clasificar") parts.push(buyer);
  return parts.join(" · ");
}

export function buildPorQueImporta(
  prospect: LeadProspectDetailUi,
  detail: LeadProspectDetailResponseUi | null,
): PorQueImportaContent {
  const evidenceNote =
    prospect.evidence_note?.trim() ||
    detail?.evidence?.[0]?.evidence_note?.trim() ||
    null;

  const likely = prospect.likely_need?.trim() || null;
  const angle = prospect.product_angle?.trim() || null;
  const necesidadProbable = likely || angle;

  const whyFromRecommendation = detail?.recommendation?.why_this_lead?.trim();
  const whyDuplicate =
    whyFromRecommendation &&
    angle &&
    whyFromRecommendation.replace(/\s*·\s*/g, " ").includes(angle);

  let porQueInteresante = "";
  if (prospect.classification === "research_only_contact_needed") {
    porQueInteresante =
      `${prospect.organization_name} aparece en investigación pública, pero aún no hay correo directo. ` +
      "Conviene ubicar responsable de laboratorio, compras o contacto institucional antes de escribir.";
  } else if (prospect.classification === "same_domain_contacted_review") {
    porQueInteresante =
      "El dominio ya tiene historial con OrigenLab. Vale la pena revisar si conviene un seguimiento a otra persona o esperar respuesta.";
  } else if (prospect.classification === "public_tender_review") {
    porQueInteresante =
      "Oportunidad de compra pública: priorizar lectura de bases, requisitos técnicos y equivalencia antes que un correo frío.";
  } else if (evidenceNote) {
    const context = sectorHint(prospect.sector, prospect.buyer_type);
    porQueInteresante = context
      ? `${evidenceNote} Contexto: ${context}.`
      : evidenceNote;
    if (angle && !porQueInteresante.toLowerCase().includes(angle.toLowerCase())) {
      porQueInteresante += ` Puede requerir ${angle.replaceAll(";", ", ")}.`;
    }
  } else {
    const context = sectorHint(prospect.sector, prospect.buyer_type);
    porQueInteresante =
      context ||
      `Organización identificada en investigación DeepSearch con encaje en ${firstProductTopic(prospect.product_angle)}.`;
  }

  if (!whyDuplicate && whyFromRecommendation && whyFromRecommendation !== necesidadProbable) {
    const extra = whyFromRecommendation.split("·")[0]?.trim();
    if (extra && !porQueInteresante.includes(extra)) {
      porQueInteresante = `${porQueInteresante} ${extra}`.trim();
    }
  }

  return {
    queHaceEvidencia: evidenceNote,
    necesidadProbable,
    porQueInteresante,
  };
}

export function buildMessagePreview(
  prospect: LeadProspectDetailUi,
  recommendation?: LeadProspectRecommendationUi | null,
): MessagePreviewContent {
  if (prospect.is_blocked) {
    return { kind: "none", title: "No hay mensaje sugerido", note: "Prospecto bloqueado." };
  }

  if (prospect.classification === "public_tender_review") {
    return {
      kind: "public_tender",
      title: "Licitación — sin correo frío",
      note: "Revisar bases y preparar equivalencia técnica / ficha del equipo. No usar plantilla de prospección genérica.",
    };
  }

  if (!hasProspectEmail(prospect)) {
    return {
      kind: "none",
      title: "No hay email directo disponible",
      note: "Próxima acción: buscar responsable de laboratorio, compras o contacto institucional.",
    };
  }

  if (prospect.classification === "manual_outreach_sent") {
    return {
      kind: "none",
      title: "Ya contactado recientemente",
      note: "Outreach manual enviado. Esperar respuesta antes de reenviar.",
    };
  }

  if (prospect.classification === "research_only_contact_needed") {
    return {
      kind: "none",
      title: "No hay mensaje sugerido",
      note: "Sin email público: investigar contacto antes de redactar.",
    };
  }

  const org = prospect.organization_name;
  const topic = firstProductTopic(prospect.product_angle);
  const angle = prospect.spanish_message_angle?.trim();

  if (
    prospect.classification === "old_gmail_prospect_review" ||
    prospect.classification === "old_followup_review"
  ) {
    const subject = recommendation?.suggested_subject?.trim();
    const body = recommendation?.suggested_body_preview?.trim();
    if (subject && body) {
      return {
        kind: "gmail_draft",
        title: "Borrador sugerido (solo vista — no envía desde el panel)",
        subject,
        body,
        note:
          recommendation?.safety_note ??
          "Revisión humana requerida. Ajustar tono y datos antes de contactar.",
      };
    }
    return {
      kind: "none",
      title: "Sin borrador cargado",
      note: "Revisar historial Gmail y redactar mensaje manualmente.",
    };
  }

  if (prospect.classification === "same_domain_contacted_review") {
    return {
      kind: "same_domain_followup",
      title: "Borrador de seguimiento, no correo frío",
      note: "Este dominio ya tiene historial en OrigenLab. Revisar correos previos antes de enviar.",
      subject: "Seguimiento — equipos de laboratorio OrigenLab",
      body: [
        `Estimados/as equipo de ${org},`,
        "",
        "Vimos que anteriormente habíamos enviado información a su institución desde OrigenLab.",
        angle
          ? `${angle}`
          : `Quería consultar si este año están evaluando reposición o compra de ${topic}.`,
        "",
        "Si corresponde, puedo compartir referencias técnicas o una cotización referencial según su necesidad.",
        "",
        "Quedo atenta a su comentario.",
        "Saludos cordiales,",
        "OrigenLab",
      ].join("\n"),
    };
  }

  if (prospect.classification === "net_new_safe_review") {
    const subject =
      topic.includes("control") || topic.includes("calidad")
        ? "Equipos para control de calidad y preparación de muestras"
        : `Consulta por equipos de laboratorio — ${org}`;

    const body = [
      `Estimados/as equipo de ${org},`,
      "",
      angle
        ? `${angle}`
        : `En OrigenLab apoyamos laboratorios con ${topic} y equipamiento de apoyo para análisis rutinarios.`,
      "",
      "¿Están evaluando reposición, compra o cotización referencial de equipos durante este semestre?",
      "Si lo indican, preparo una propuesta acotada a su necesidad (marca, capacidad y normativa aplicable).",
      "",
      "Saludos cordiales,",
      "OrigenLab",
    ].join("\n");

    return {
      kind: "net_new",
      title: "Mensaje sugerido (solo vista — no envía desde el panel)",
      subject,
      body,
      note: "Revisión humana requerida. Ajustar tono y datos antes de contactar.",
    };
  }

  return { kind: "none", title: "No hay mensaje sugerido" };
}

export function shouldShowMessageSection(preview: MessagePreviewContent): boolean {
  return (
    preview.kind === "net_new" ||
    preview.kind === "same_domain_followup" ||
    preview.kind === "gmail_draft"
  );
}
