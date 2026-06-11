import type { WarmCaseCategory, WarmCaseItem } from "../api/commercialTypes";
import { emailDomain, parseSortableTimestamp } from "./clientTableView";
import { formatDashboardDateTime } from "./dashboardDateFormat";
import { truncate } from "./safeText";

export interface SupplierGroupDefinition {
  id: string;
  label: string;
  domains: readonly string[];
}

/** Known supplier entities for grouped operator view (Phase 7B.3). */
export const SUPPLIER_GROUP_DEFINITIONS: readonly SupplierGroupDefinition[] = [
  { id: "serva", label: "SERVA", domains: ["serva.de"] },
  { id: "ika", label: "IKA", domains: ["ika.net.br"] },
  { id: "ortoalresa", label: "Ortoalresa", domains: ["ortoalresa.com"] },
  { id: "hielscher", label: "Hielscher", domains: ["hielscher.com"] },
  { id: "ollital", label: "Ollital", domains: ["ollital.com"] },
  { id: "dlab", label: "DLAB", domains: ["dlabsci.com"] },
] as const;

const QUOTE_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "supplier_quote_received",
  "supplier_reply",
]);

const FOLLOWUP_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "supplier_followup",
  "waiting_supplier",
]);

export type SupplierRoleBadge = "Cotización recibida" | "Seguimiento" | "Hilo activo";

export interface SupplierEntityGroup {
  id: string;
  label: string;
  count: number;
  summaryLabel: string;
  quoteCount: number;
  followupCount: number;
  latestSeenAt: string | null;
  latestActivityLabel: string | null;
  latestSubject: string;
  roleBadge: SupplierRoleBadge;
  items: WarmCaseItem[];
}

function latestItem(items: WarmCaseItem[]): WarmCaseItem | null {
  if (items.length === 0) {
    return null;
  }
  return [...items].sort(
    (a, b) => parseSortableTimestamp(b.last_seen_at) - parseSortableTimestamp(a.last_seen_at),
  )[0];
}

export function roleBadgeForCategory(category: WarmCaseCategory | undefined): SupplierRoleBadge {
  if (!category) {
    return "Hilo activo";
  }
  if (QUOTE_CATEGORIES.has(category)) {
    return "Cotización recibida";
  }
  if (FOLLOWUP_CATEGORIES.has(category)) {
    return "Seguimiento";
  }
  return "Hilo activo";
}

export function buildSupplierCaseSummary(items: WarmCaseItem[]): string {
  const n = items.length;
  const casoLabel = `${n} ${n === 1 ? "caso" : "casos"}`;
  const groupedTotal = items.reduce((sum, row) => sum + (row.grouped_email_count ?? 1), 0);
  if (groupedTotal > n) {
    return `${casoLabel} · ${groupedTotal} correos agrupados`;
  }
  return n === 1 ? "1 caso activo" : `${n} casos activos`;
}

function previewSubject(row: WarmCaseItem | null): string {
  if (!row) {
    return "—";
  }
  const raw = row.subject?.trim() || row.snippet?.trim() || "";
  return raw ? truncate(raw, 72) : "—";
}

function formatActivityDate(iso: string | null): string | null {
  if (!iso?.trim()) {
    return null;
  }
  const formatted = formatDashboardDateTime(iso);
  return formatted === "—" ? null : formatted;
}

function buildGroup(id: string, label: string, items: WarmCaseItem[]): SupplierEntityGroup {
  const latest = latestItem(items);
  return {
    id,
    label,
    count: items.length,
    summaryLabel: buildSupplierCaseSummary(items),
    quoteCount: items.filter((row) => QUOTE_CATEGORIES.has(row.category)).length,
    followupCount: items.filter((row) => FOLLOWUP_CATEGORIES.has(row.category)).length,
    latestSeenAt: latest?.last_seen_at ?? null,
    latestActivityLabel: formatActivityDate(latest?.last_seen_at ?? null),
    latestSubject: previewSubject(latest),
    roleBadge: roleBadgeForCategory(latest?.category),
    items,
  };
}

export function resolveSupplierGroupId(row: WarmCaseItem): string {
  const domain = emailDomain(row.contact_email);
  for (const def of SUPPLIER_GROUP_DEFINITIONS) {
    if (def.domains.includes(domain)) {
      return def.id;
    }
  }
  const org = (row.account_name || "").trim().toLowerCase();
  for (const def of SUPPLIER_GROUP_DEFINITIONS) {
    if (org.includes(def.label.toLowerCase())) {
      return def.id;
    }
  }
  if (domain) {
    return `domain:${domain}`;
  }
  return "other";
}

export function groupSupplierWarmCases(items: WarmCaseItem[]): SupplierEntityGroup[] {
  const buckets = new Map<string, WarmCaseItem[]>();

  for (const row of items) {
    const id = resolveSupplierGroupId(row);
    const list = buckets.get(id) ?? [];
    list.push(row);
    buckets.set(id, list);
  }

  const known: SupplierEntityGroup[] = [];
  for (const def of SUPPLIER_GROUP_DEFINITIONS) {
    const groupItems = buckets.get(def.id) ?? [];
    if (groupItems.length === 0) {
      continue;
    }
    known.push(buildGroup(def.id, def.label, groupItems));
    buckets.delete(def.id);
  }

  const extras: SupplierEntityGroup[] = [];
  for (const [id, groupItems] of buckets) {
    if (groupItems.length === 0) {
      continue;
    }
    const label =
      id === "other"
        ? "Otros proveedores"
        : id.startsWith("domain:")
          ? id.replace("domain:", "")
          : id;
    extras.push(buildGroup(id, label, groupItems));
  }

  extras.sort((a, b) => b.count - a.count);
  return [...known, ...extras];
}
