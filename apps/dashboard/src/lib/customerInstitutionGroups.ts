import type { LeadProspectListItemUi } from "../api/leadIntelTypes";
import { hasProspectEmail, parseRiskFlagChips } from "./prospectLabels";

export type InstitutionViewPreset =
  | "all"
  | "contact_review"
  | "gmail_history"
  | "missing_email"
  | "blocked_risk";

export type InstitutionType =
  | "hospital_clinica"
  | "universidad"
  | "laboratorio_servicio"
  | "laboratorio_publico_instituto"
  | "agua_ambiente"
  | "alimentos_agro"
  | "farmaceutica_biotec"
  | "mineria_industria_qc"
  | "centro_id_tecnologico"
  | "proveedor_vendor"
  | "otro_revisar";

export const INSTITUTION_TYPE_OPTIONS: ReadonlyArray<{
  value: InstitutionType | "";
  label: string;
}> = [
  { value: "", label: "Todas" },
  { value: "hospital_clinica", label: "Hospital / clínica" },
  { value: "universidad", label: "Universidad" },
  { value: "laboratorio_servicio", label: "Laboratorio de servicio" },
  { value: "laboratorio_publico_instituto", label: "Laboratorio público / instituto" },
  { value: "agua_ambiente", label: "Agua / ambiente" },
  { value: "alimentos_agro", label: "Alimentos / agro" },
  { value: "farmaceutica_biotec", label: "Farmacéutica / biotec" },
  { value: "mineria_industria_qc", label: "Minería / industria QC" },
  { value: "centro_id_tecnologico", label: "Centro I+D / tecnológico" },
  { value: "proveedor_vendor", label: "Proveedor / vendor" },
  { value: "otro_revisar", label: "Otro / revisar" },
];

export interface CustomerInstitutionFilters {
  institutionType: InstitutionType | "";
  sector: string;
  region: string;
  minScore: number | null;
}

export interface InstitutionStatusChip {
  code: string;
  label: string;
  className: string;
}

export interface CustomerInstitutionGroup {
  key: string;
  institutionName: string;
  domain: string | null;
  sectors: string[];
  regions: string[];
  buyerTypes: string[];
  contactsWithEmail: number;
  contactsMissingEmail: number;
  totalRows: number;
  maxFinalScore: number;
  anyBlocked: boolean;
  anyRisk: boolean;
  hasGmailHistory: boolean;
  totalGmailSent: number;
  totalGmailReceived: number;
  latestGmailLastContactedAt: string | null;
  latestSafeSubject: string | null;
  campaignBuckets: string[];
  sourceTypes: string[];
  institutionTypes: InstitutionType[];
  rows: LeadProspectListItemUi[];
  recommendedNextAction: string;
}

function blob(row: LeadProspectListItemUi): string {
  return [
    row.organization_name,
    row.domain,
    row.sector,
    row.buyer_type,
    row.risk_flags,
    row.source_type,
    row.classification,
  ]
    .map((value) => normalizeText(value))
    .join(" ");
}

export function deriveInstitutionType(row: LeadProspectListItemUi): InstitutionType {
  const text = blob(row);
  if (
    row.classification === "supplier_or_internal_block" ||
    text.includes("proveedor") ||
    text.includes("vendor") ||
    text.includes("supplier") ||
    text.includes("interno")
  ) {
    return "proveedor_vendor";
  }
  if (
    text.includes("hospital") ||
    text.includes("clinica") ||
    text.includes("clínica") ||
    text.includes("redsalud") ||
    text.includes("salud") ||
    row.buyer_type?.includes("hospital")
  ) {
    return "hospital_clinica";
  }
  if (
    text.includes("universidad") ||
    text.includes("university") ||
    row.buyer_type?.includes("universidad") ||
    row.campaign_bucket === "university"
  ) {
    return "universidad";
  }
  if (
    text.includes("agua") ||
    text.includes("ambiente") ||
    text.includes("acuicola") ||
    text.includes("acuícola") ||
    row.buyer_type?.includes("acuicola")
  ) {
    return "agua_ambiente";
  }
  if (text.includes("alimento") || text.includes("agro") || text.includes("food")) {
    return "alimentos_agro";
  }
  if (
    text.includes("farma") ||
    text.includes("biotec") ||
    text.includes("biotech") ||
    text.includes("biofarma")
  ) {
    return "farmaceutica_biotec";
  }
  if (
    text.includes("mineria") ||
    text.includes("minería") ||
    text.includes("industria") ||
    text.includes("qc") ||
    text.includes("control de calidad")
  ) {
    return "mineria_industria_qc";
  }
  if (
    text.includes("instituto") ||
    text.includes("publico") ||
    text.includes("público") ||
    row.buyer_type?.includes("publico")
  ) {
    return "laboratorio_publico_instituto";
  }
  if (
    text.includes("investigacion") ||
    text.includes("investigación") ||
    text.includes("i+d") ||
    text.includes("id ") ||
    text.includes("tecnolog") ||
    row.buyer_type?.includes("investigacion") ||
    row.buyer_type?.includes("centro_investigacion")
  ) {
    return "centro_id_tecnologico";
  }
  if (
    text.includes("laboratorio") ||
    row.buyer_type?.includes("laboratorio") ||
    row.sector?.toLowerCase().includes("laboratorio")
  ) {
    return "laboratorio_servicio";
  }
  return "otro_revisar";
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function uniqueNonEmpty(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const trimmed = value?.trim();
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out.sort((a, b) => a.localeCompare(b, "es"));
}

function rowHasGmailHistory(row: LeadProspectListItemUi): boolean {
  return (
    (row.gmail_sent_count ?? 0) > 0 ||
    (row.gmail_received_count ?? 0) > 0 ||
    Boolean(row.gmail_last_contacted_at?.trim()) ||
    row.source_type === "gmail_historico" ||
    row.source_type === "followup_antiguo"
  );
}

function rowHasRisk(row: LeadProspectListItemUi): boolean {
  if (row.is_blocked) return true;
  return parseRiskFlagChips(row.risk_flags).length > 0;
}

function isBuyerProspectRow(row: LeadProspectListItemUi): boolean {
  if (row.classification === "supplier_or_internal_block") return false;
  const flags = (row.risk_flags ?? "").toLowerCase();
  if (flags.includes("proveedor") || flags.includes("interno")) return false;
  return true;
}

function pickLatestIso(dates: Array<string | null | undefined>): string | null {
  const parsed = dates
    .map((value) => value?.trim())
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => b.localeCompare(a));
  return parsed[0] ?? null;
}

export function normalizeInstitutionKey(row: LeadProspectListItemUi): string {
  const domain = normalizeText(row.domain);
  if (domain) return `domain:${domain}`;
  const org = normalizeText(row.organization_name);
  if (org) return `org:${org}`;
  return `prospect:${row.prospect_key}`;
}

export function institutionNextAction(group: CustomerInstitutionGroup): string {
  if (group.anyBlocked || group.anyRisk) {
    return "Revisar bloqueo / riesgo antes de contactar";
  }
  if (group.contactsMissingEmail > 0 && group.contactsWithEmail === 0) {
    return "Investigar email de contacto";
  }
  if (group.hasGmailHistory) {
    return "Dar seguimiento con historial Gmail";
  }
  if (group.contactsMissingEmail > 0) {
    return "Completar contacto faltante antes de outreach";
  }
  return "Revisar y contactar manualmente";
}

export function institutionStatusChips(group: CustomerInstitutionGroup): InstitutionStatusChip[] {
  const chips: InstitutionStatusChip[] = [];
  if (group.hasGmailHistory) {
    chips.push({
      code: "gmail_history",
      label: "Gmail en espejo",
      className: "border-sky-200 bg-sky-50 text-sky-950",
    });
  }
  const gmailDetected = group.totalGmailSent + group.totalGmailReceived;
  if (gmailDetected > 0) {
    chips.push({
      code: "gmail_detected",
      label: `${gmailDetected} Gmail detectado`,
      className: "border-indigo-200 bg-indigo-50 text-indigo-950",
    });
  }
  if (group.contactsMissingEmail > 0) {
    chips.push({
      code: "missing_email",
      label: "Falta email",
      className: "border-amber-200 bg-amber-50 text-amber-950",
    });
  }
  if (group.anyBlocked) {
    chips.push({
      code: "blocked",
      label: "Bloqueado",
      className: "border-red-200 bg-red-50 text-red-900",
    });
  }
  if (group.maxFinalScore >= 85 && !group.anyBlocked) {
    chips.push({
      code: "high_priority",
      label: "Alta prioridad",
      className: "border-teal-200 bg-teal-50 text-teal-950",
    });
  }
  if (group.sourceTypes.includes("deepsearch")) {
    chips.push({
      code: "deepsearch",
      label: "DeepSearch",
      className: "border-violet-200 bg-violet-50 text-violet-950",
    });
  }
  return chips;
}

export function buildCustomerInstitutionGroups(
  rows: LeadProspectListItemUi[],
): CustomerInstitutionGroup[] {
  const buyerRows = rows.filter(isBuyerProspectRow);
  const byKey = new Map<string, LeadProspectListItemUi[]>();

  for (const row of buyerRows) {
    const key = normalizeInstitutionKey(row);
    const bucket = byKey.get(key) ?? [];
    bucket.push(row);
    byKey.set(key, bucket);
  }

  const groups: CustomerInstitutionGroup[] = [];
  for (const [key, institutionRows] of byKey.entries()) {
    const domain = uniqueNonEmpty(institutionRows.map((row) => row.domain))[0] ?? null;
    const institutionName =
      uniqueNonEmpty(institutionRows.map((row) => row.organization_name))[0] ?? "Institución sin nombre";
    const contactsWithEmail = institutionRows.filter((row) => hasProspectEmail(row)).length;
    const contactsMissingEmail = institutionRows.length - contactsWithEmail;
    const anyBlocked = institutionRows.some((row) => row.is_blocked);
    const anyRisk = institutionRows.some((row) => rowHasRisk(row));
    const hasGmailHistory = institutionRows.some((row) => rowHasGmailHistory(row));

    const groupBase: CustomerInstitutionGroup = {
      key,
      institutionName,
      domain,
      sectors: uniqueNonEmpty(institutionRows.map((row) => row.sector)),
      regions: uniqueNonEmpty(institutionRows.map((row) => row.region)),
      buyerTypes: uniqueNonEmpty(institutionRows.map((row) => row.buyer_type)),
      contactsWithEmail,
      contactsMissingEmail,
      totalRows: institutionRows.length,
      maxFinalScore: Math.max(...institutionRows.map((row) => row.final_score ?? 0), 0),
      anyBlocked,
      anyRisk,
      hasGmailHistory,
      totalGmailSent: institutionRows.reduce((sum, row) => sum + (row.gmail_sent_count ?? 0), 0),
      totalGmailReceived: institutionRows.reduce(
        (sum, row) => sum + (row.gmail_received_count ?? 0),
        0,
      ),
      latestGmailLastContactedAt: pickLatestIso(
        institutionRows.map((row) => row.gmail_last_contacted_at),
      ),
      latestSafeSubject:
        institutionRows.find((row) => row.gmail_latest_subject_safe?.trim())?.gmail_latest_subject_safe ??
        null,
      campaignBuckets: uniqueNonEmpty(institutionRows.map((row) => row.campaign_bucket)),
      sourceTypes: uniqueNonEmpty(institutionRows.map((row) => row.source_type)),
      institutionTypes: uniqueNonEmpty(
        institutionRows.map((row) => deriveInstitutionType(row)),
      ) as InstitutionType[],
      rows: [...institutionRows].sort((a, b) => b.final_score - a.final_score),
      recommendedNextAction: "",
    };
    groupBase.recommendedNextAction = institutionNextAction(groupBase);
    groups.push(groupBase);
  }

  return groups.sort((a, b) => {
    if (b.maxFinalScore !== a.maxFinalScore) return b.maxFinalScore - a.maxFinalScore;
    return a.institutionName.localeCompare(b.institutionName, "es");
  });
}

export function filterCustomerInstitutionGroups(
  groups: CustomerInstitutionGroup[],
  filters: CustomerInstitutionFilters,
): CustomerInstitutionGroup[] {
  return groups.filter((group) => {
    if (filters.institutionType) {
      if (!group.institutionTypes.includes(filters.institutionType)) return false;
    }
    if (filters.sector.trim()) {
      const sector = normalizeText(filters.sector);
      if (!group.sectors.some((value) => normalizeText(value).includes(sector))) return false;
    }
    if (filters.region.trim()) {
      const region = normalizeText(filters.region);
      if (!group.regions.some((value) => normalizeText(value).includes(region))) return false;
    }
    if (filters.minScore != null && group.maxFinalScore < filters.minScore) return false;
    return true;
  });
}

export function institutionKpis(groups: CustomerInstitutionGroup[]) {
  return {
    institutions: groups.length,
    withGmailHistory: groups.filter((group) => group.hasGmailHistory).length,
    missingEmail: groups.filter((group) => group.contactsMissingEmail > 0).length,
    safeToReview: groups.filter(
      (group) => !group.anyBlocked && !group.anyRisk && group.contactsWithEmail > 0,
    ).length,
    blockedOrRisk: groups.filter((group) => group.anyBlocked || group.anyRisk).length,
  };
}
