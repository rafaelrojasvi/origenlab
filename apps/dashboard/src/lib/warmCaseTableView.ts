import type { WarmCaseCategory, WarmCaseItem, WarmCaseStatus } from "../api/commercialTypes";
import { emailDomain, matchesSearch, normalizeSearchQuery, parseSortableTimestamp } from "./clientTableView";
import { isInternalOperatorContact } from "./internalContactFilter";
import {
  DEFAULT_WARM_VIEW_PRESET,
  filterWarmCasesByViewPreset,
  type WarmCaseViewPreset,
} from "./warmCaseViewPreset";

export type WarmCaseSortKey = "last_seen_desc" | "last_seen_asc" | "status" | "category" | "contact";

export interface WarmCaseTableFilters {
  search: string;
  status: WarmCaseStatus | "";
  category: WarmCaseCategory | "";
  sort: WarmCaseSortKey;
  /** When true, hide @origenlab.cl and @labdelivery.cl (client-side only). Default on. */
  hideInternalContacts: boolean;
  /** Queue focus preset (client-side). Default: real client threads. */
  preset: WarmCaseViewPreset;
}

export const DEFAULT_WARM_FILTERS: WarmCaseTableFilters = {
  search: "",
  status: "",
  category: "",
  sort: "last_seen_desc",
  hideInternalContacts: true,
  preset: DEFAULT_WARM_VIEW_PRESET,
};

/** Resets search/status/category and view preset to Clientes reales (initial load state). */
export function clearWarmCaseTableFilters(): WarmCaseTableFilters {
  return { ...DEFAULT_WARM_FILTERS };
}

const STATUS_ORDER: Record<WarmCaseStatus, number> = {
  problem: 0,
  new: 1,
  open: 2,
  waiting: 3,
  quoted: 4,
};

const CATEGORY_ORDER: Record<WarmCaseCategory, number> = {
  bounce: 0,
  auto_reply: 1,
  payment_admin: 2,
  payment_received: 2,
  vendor_logistics: 3,
  client_reply: 4,
  supplier_reply: 5,
  quote_sent: 6,
  waiting_supplier: 7,
  waiting_client: 8,
  opportunity: 9,
};

export function warmCaseSearchHaystack(row: WarmCaseItem): string {
  return [
    row.contact_email,
    emailDomain(row.contact_email),
    row.account_name,
    row.subject,
    row.snippet,
    row.equipment_signal,
    row.next_action,
  ]
    .join(" ")
    .toLowerCase();
}

export function filterWarmCases(items: WarmCaseItem[], filters: WarmCaseTableFilters): WarmCaseItem[] {
  const q = normalizeSearchQuery(filters.search);
  return items.filter((row) => {
    if (filters.hideInternalContacts && isInternalOperatorContact(row.contact_email)) {
      return false;
    }
    if (filters.status && row.status !== filters.status) {
      return false;
    }
    if (filters.category && row.category !== filters.category) {
      return false;
    }
    if (q && !matchesSearch(warmCaseSearchHaystack(row), q)) {
      return false;
    }
    return true;
  });
}

function compareWarmCases(a: WarmCaseItem, b: WarmCaseItem, sort: WarmCaseSortKey): number {
  switch (sort) {
    case "last_seen_asc":
      return parseSortableTimestamp(a.last_seen_at) - parseSortableTimestamp(b.last_seen_at);
    case "last_seen_desc":
      return parseSortableTimestamp(b.last_seen_at) - parseSortableTimestamp(a.last_seen_at);
    case "status":
      return (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99);
    case "category":
      return (CATEGORY_ORDER[a.category] ?? 99) - (CATEGORY_ORDER[b.category] ?? 99);
    case "contact":
      return a.contact_email.localeCompare(b.contact_email);
    default:
      return 0;
  }
}

export function sortWarmCases(items: WarmCaseItem[], sort: WarmCaseSortKey): WarmCaseItem[] {
  return [...items].sort((a, b) => compareWarmCases(a, b, sort));
}

export function applyWarmCaseTableView(
  items: WarmCaseItem[],
  filters: WarmCaseTableFilters,
): WarmCaseItem[] {
  const byPreset = filterWarmCasesByViewPreset(items, filters.preset);
  return sortWarmCases(filterWarmCases(byPreset, filters), filters.sort);
}

export function warmFiltersActive(filters: WarmCaseTableFilters): boolean {
  return Boolean(
    filters.search.trim() ||
      filters.status ||
      filters.category ||
      filters.preset !== DEFAULT_WARM_VIEW_PRESET ||
      !filters.hideInternalContacts,
  );
}

export type { WarmCaseViewPreset } from "./warmCaseViewPreset";
export {
  DEFAULT_WARM_VIEW_PRESET,
  WARM_VIEW_PRESET_LABELS,
  WARM_VIEW_PRESET_ORDER,
  matchesWarmCaseViewPreset,
} from "./warmCaseViewPreset";

export function uniqueWarmStatuses(items: WarmCaseItem[]): WarmCaseStatus[] {
  const set = new Set<WarmCaseStatus>();
  for (const row of items) {
    if (row.status) {
      set.add(row.status);
    }
  }
  return [...set].sort();
}

export function uniqueWarmCategories(items: WarmCaseItem[]): WarmCaseCategory[] {
  const set = new Set<WarmCaseCategory>();
  for (const row of items) {
    if (row.category) {
      set.add(row.category);
    }
  }
  return [...set].sort();
}
