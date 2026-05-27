const CLASSIFICATION_LABELS: Record<string, string> = {
  net_new_safe_review: "Prospecto nuevo seguro",
  same_domain_contacted_review: "Revisar: dominio ya contactado",
  public_tender_review: "Licitación / compra pública",
  research_only_contact_needed: "Falta contacto directo",
  already_contacted_block: "Bloqueado: ya contactado",
  bounced_block: "Bloqueado: rebote",
  suppressed_block: "Bloqueado: suprimido",
  supplier_or_internal_block: "Bloqueado: proveedor / interno",
};

const STATUS_LABELS: Record<string, string> = {
  net_new_safe_review: "Prospecto nuevo seguro",
  same_domain_review: "Revisar dominio",
  public_tender_review: "Licitación pública",
  research_needed: "Falta email",
  blocked: "Bloqueado",
  review_only: "En revisión",
};

export function leadClassificationLabel(code: string): string {
  return CLASSIFICATION_LABELS[code] ?? STATUS_LABELS[code] ?? code;
}

export function leadStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? leadClassificationLabel(status);
}

export function leadCampaignBucketLabel(bucket: string | null | undefined): string {
  if (!bucket) return "—";
  const map: Record<string, string> = {
    private_lab: "Laboratorio privado",
    public_tender: "Licitación pública",
    university: "Universidad / investigación",
    same_domain: "Mismo dominio",
    blocked: "Bloqueado",
    other: "Otro",
  };
  return map[bucket] ?? bucket;
}

export function prospectSafetyBanner(classification: string, isBlocked: boolean): string | null {
  if (isBlocked) {
    return "No contactar — prospecto bloqueado por historial OrigenLab.";
  }
  if (classification === "same_domain_contacted_review") {
    return "Ya existe historial con este dominio. Revisar conversación previa antes de escribir.";
  }
  if (classification === "public_tender_review") {
    return "Ruta recomendada: revisar bases / preparar equivalencia técnica, no email frío genérico.";
  }
  return "No enviar sin revisión humana.";
}
