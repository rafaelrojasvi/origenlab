import type { LeadProspectListItemUi } from "../api/leadIntelTypes";
import { hasProspectEmail, parseRiskFlagChips } from "./prospectLabels";

export type InstitutionViewPreset =
  | "all"
  | "contact_review"
  | "gmail_history"
  | "missing_email"
  | "blocked_risk";

export interface CustomerInstitutionFilters {
  search: string;
  preset: InstitutionViewPreset;
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
  rows: LeadProspectListItemUi[];
  recommendedNextAction: string;
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

function groupMatchesSearch(group: CustomerInstitutionGroup, search: string): boolean {
  const q = normalizeText(search);
  if (!q) return true;
  if (normalizeText(group.institutionName).includes(q)) return true;
  if (normalizeText(group.domain).includes(q)) return true;
  return group.rows.some(
    (row) =>
      normalizeText(row.email).includes(q) ||
      normalizeText(row.contact_name).includes(q) ||
      normalizeText(row.organization_name).includes(q),
  );
}

export function filterCustomerInstitutionGroups(
  groups: CustomerInstitutionGroup[],
  filters: CustomerInstitutionFilters,
): CustomerInstitutionGroup[] {
  return groups.filter((group) => {
    if (!groupMatchesSearch(group, filters.search)) return false;
    if (filters.sector.trim()) {
      const sector = normalizeText(filters.sector);
      if (!group.sectors.some((value) => normalizeText(value).includes(sector))) return false;
    }
    if (filters.region.trim()) {
      const region = normalizeText(filters.region);
      if (!group.regions.some((value) => normalizeText(value).includes(region))) return false;
    }
    if (filters.minScore != null && group.maxFinalScore < filters.minScore) return false;

    switch (filters.preset) {
      case "contact_review":
        return !group.anyBlocked && (group.contactsWithEmail > 0 || group.maxFinalScore >= 70);
      case "gmail_history":
        return group.hasGmailHistory;
      case "missing_email":
        return group.contactsMissingEmail > 0;
      case "blocked_risk":
        return group.anyBlocked || group.anyRisk;
      default:
        return true;
    }
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
