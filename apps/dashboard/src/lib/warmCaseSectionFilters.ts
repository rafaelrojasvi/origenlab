import type { WarmCaseCategory, WarmCaseItem } from "../api/commercialTypes";
import { matchesWarmCaseViewPreset } from "./warmCaseViewPreset";

const SUPPLIER_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "supplier_quote_received",
  "supplier_followup",
  "supplier_reply",
]);

const PAYMENTS_LOGISTICS_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "payment_admin",
  "payment_received",
  "logistics_admin",
  "vendor_logistics",
]);

const CLIENT_OPPORTUNITY_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "client_opportunity",
  "opportunity",
  "client_response",
  "client_reply",
]);

export function filterSupplierWarmCases(items: WarmCaseItem[]): WarmCaseItem[] {
  return items.filter(
    (row) =>
      SUPPLIER_CATEGORIES.has(row.category) || matchesWarmCaseViewPreset(row, "proveedores"),
  );
}

export function filterPaymentsLogisticsWarmCases(items: WarmCaseItem[]): WarmCaseItem[] {
  return items.filter(
    (row) =>
      PAYMENTS_LOGISTICS_CATEGORIES.has(row.category) ||
      matchesWarmCaseViewPreset(row, "pagos_admin") ||
      matchesWarmCaseViewPreset(row, "logistica"),
  );
}

export function isClientOpportunityWarmCase(row: WarmCaseItem): boolean {
  return CLIENT_OPPORTUNITY_CATEGORIES.has(row.category);
}
