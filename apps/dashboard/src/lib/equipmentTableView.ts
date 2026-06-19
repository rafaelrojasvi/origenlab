import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import type { EquipmentTriageBadgeKey } from "./equipmentTriage";
import { getEquipmentTriageBadges } from "./equipmentTriage";
import { getEquipmentWatchlistKey } from "./equipmentWatchlist";
import { matchesSearch, normalizeSearchQuery, parseSortableTimestamp } from "./clientTableView";

export type EquipmentSortKey =
  | "rank_asc"
  | "rank_desc"
  | "close_date_asc"
  | "close_date_desc"
  | "category"
  | "buyer";

export type EquipmentTriageFilter = EquipmentTriageBadgeKey | "all";
export type EquipmentWatchlistFilter = "all" | "saved";

export interface EquipmentTableFilters {
  search: string;
  sort: EquipmentSortKey;
  triage: EquipmentTriageFilter;
  watchlist: EquipmentWatchlistFilter;
}

export const DEFAULT_EQUIPMENT_FILTERS: EquipmentTableFilters = {
  search: "",
  sort: "rank_asc",
  triage: "all",
  watchlist: "all",
};

export interface EquipmentTableViewOptions {
  now?: Date;
  savedKeys?: Set<string>;
}

export function equipmentSearchHaystack(row: EquipmentOpportunityItem): string {
  return [
    row.buyer,
    row.region,
    row.equipment_category,
    row.item_description,
    row.operator_note,
    row.codigo_licitacion,
    row.contact_status,
    row.next_action,
    row.safe_channel,
  ]
    .join(" ")
    .toLowerCase();
}

function matchesTriageFilter(
  row: EquipmentOpportunityItem,
  triage: EquipmentTriageFilter,
  now?: Date,
): boolean {
  if (triage === "all") {
    return true;
  }
  return getEquipmentTriageBadges(row, { now }).some((badge) => badge.key === triage);
}

function matchesWatchlistFilter(
  row: EquipmentOpportunityItem,
  watchlist: EquipmentWatchlistFilter,
  savedKeys?: Set<string>,
): boolean {
  if (watchlist === "all") {
    return true;
  }
  return (savedKeys ?? new Set()).has(getEquipmentWatchlistKey(row));
}

export function filterEquipment(
  items: EquipmentOpportunityItem[],
  filters: EquipmentTableFilters,
  options?: EquipmentTableViewOptions,
): EquipmentOpportunityItem[] {
  const q = normalizeSearchQuery(filters.search);
  return items.filter((row) => {
    if (q && !matchesSearch(equipmentSearchHaystack(row), q)) {
      return false;
    }
    if (!matchesTriageFilter(row, filters.triage, options?.now)) {
      return false;
    }
    return matchesWatchlistFilter(row, filters.watchlist, options?.savedKeys);
  });
}

function compareEquipment(a: EquipmentOpportunityItem, b: EquipmentOpportunityItem, sort: EquipmentSortKey): number {
  switch (sort) {
    case "rank_asc":
      return (a.priority_rank ?? 0) - (b.priority_rank ?? 0);
    case "rank_desc":
      return (b.priority_rank ?? 0) - (a.priority_rank ?? 0);
    case "close_date_asc":
      return parseSortableTimestamp(a.close_date) - parseSortableTimestamp(b.close_date);
    case "close_date_desc":
      return parseSortableTimestamp(b.close_date) - parseSortableTimestamp(a.close_date);
    case "category":
      return (a.equipment_category || "").localeCompare(b.equipment_category || "");
    case "buyer":
      return (a.buyer || "").localeCompare(b.buyer || "");
    default:
      return 0;
  }
}

export function sortEquipment(items: EquipmentOpportunityItem[], sort: EquipmentSortKey): EquipmentOpportunityItem[] {
  return [...items].sort((a, b) => compareEquipment(a, b, sort));
}

export function applyEquipmentTableView(
  items: EquipmentOpportunityItem[],
  filters: EquipmentTableFilters,
  options?: EquipmentTableViewOptions,
): EquipmentOpportunityItem[] {
  return sortEquipment(filterEquipment(items, filters, options), filters.sort);
}

export function equipmentFiltersActive(filters: EquipmentTableFilters): boolean {
  return (
    Boolean(filters.search.trim()) ||
    filters.triage !== "all" ||
    filters.watchlist !== "all"
  );
}
