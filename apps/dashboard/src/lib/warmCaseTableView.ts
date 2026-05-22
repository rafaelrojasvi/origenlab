import type { WarmCaseCategory, WarmCaseItem, WarmCaseStatus } from "../api/commercialTypes";
import { emailDomain, matchesSearch, normalizeSearchQuery, parseSortableTimestamp } from "./clientTableView";
import { isInternalOperatorContact } from "./internalContactFilter";

export type WarmCaseSortKey = "last_seen_desc" | "last_seen_asc" | "status" | "category" | "contact";

export interface WarmCaseTableFilters {
  search: string;
  status: WarmCaseStatus | "";
  category: WarmCaseCategory | "";
  sort: WarmCaseSortKey;
  /** When true, hide @origenlab.cl and @labdelivery.cl (client-side only). Default off. */
  hideInternalContacts: boolean;
}

export const DEFAULT_WARM_FILTERS: WarmCaseTableFilters = {
  search: "",
  status: "",
  category: "",
  sort: "last_seen_desc",
  hideInternalContacts: false,
};

const STATUS_ORDER: Record<WarmCaseStatus, number> = {
  problem: 0,
  new: 1,
  open: 2,
  waiting: 3,
  quoted: 4,
};

const CATEGORY_ORDER: Record<WarmCaseCategory, number> = {
  bounce: 0,
  client_reply: 1,
  supplier_reply: 2,
  quote_sent: 3,
  waiting_supplier: 4,
  waiting_client: 5,
  opportunity: 6,
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
  return sortWarmCases(filterWarmCases(items, filters), filters.sort);
}

export function warmFiltersActive(filters: WarmCaseTableFilters): boolean {
  return Boolean(
    filters.search.trim() || filters.status || filters.category || filters.hideInternalContacts,
  );
}

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
