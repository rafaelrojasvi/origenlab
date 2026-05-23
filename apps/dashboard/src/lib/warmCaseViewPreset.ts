/** Client-side warm queue view presets (no API calls). */

import type { WarmCaseCategory, WarmCaseItem } from "../api/commercialTypes";
import { emailDomain } from "./clientTableView";

export type WarmCaseViewPreset =
  | "clientes_reales"
  | "proveedores"
  | "pagos_admin"
  | "logistica"
  | "con_senal_equipo"
  | "todo";

export const DEFAULT_WARM_VIEW_PRESET: WarmCaseViewPreset = "clientes_reales";

export const WARM_VIEW_PRESET_LABELS: Record<WarmCaseViewPreset, string> = {
  clientes_reales: "Clientes reales",
  proveedores: "Proveedores",
  pagos_admin: "Pagos/admin",
  logistica: "Logística",
  con_senal_equipo: "Con señal de equipo",
  todo: "Todo",
};

export const WARM_VIEW_PRESET_ORDER: WarmCaseViewPreset[] = [
  "clientes_reales",
  "proveedores",
  "pagos_admin",
  "logistica",
  "con_senal_equipo",
  "todo",
];

const CLIENTES_REALES_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "client_reply",
  "quote_sent",
  "waiting_client",
]);

const SUPPLIER_VENDOR_DOMAINS: ReadonlySet<string> = new Set([
  "ollital.com",
  "serva.de",
  "ortoalresa.com",
  "dlabsci.com",
  "crtopmachine.com",
  "asynt.com",
]);

const LOGISTICS_DOMAINS: ReadonlySet<string> = new Set(["dhl.com"]);

const PAYMENT_ADMIN_DOMAINS: ReadonlySet<string> = new Set(["bancochile.cl"]);

const PAYMENT_ADMIN_CATEGORIES: ReadonlySet<WarmCaseCategory> = new Set([
  "payment_admin",
  "payment_received",
]);

function pagosAdminTextHaystack(row: WarmCaseItem): string {
  return [row.subject, row.snippet, row.account_name].join(" ").toLowerCase();
}

function matchesPagosAdminSignals(row: WarmCaseItem): boolean {
  const hay = pagosAdminTextHaystack(row);
  return hay.includes("factura") || hay.includes("transferencia");
}

function matchesPagosAdminPreset(row: WarmCaseItem): boolean {
  if (PAYMENT_ADMIN_CATEGORIES.has(row.category)) {
    return true;
  }
  if (PAYMENT_ADMIN_DOMAINS.has(emailDomain(row.contact_email))) {
    return true;
  }
  return matchesPagosAdminSignals(row);
}

export function matchesWarmCaseViewPreset(
  row: WarmCaseItem,
  preset: WarmCaseViewPreset,
): boolean {
  if (preset === "todo") {
    return true;
  }

  const category = row.category;
  const domain = emailDomain(row.contact_email);

  switch (preset) {
    case "clientes_reales":
      return CLIENTES_REALES_CATEGORIES.has(category);

    case "proveedores":
      if (category === "vendor_logistics") {
        return false;
      }
      if (category === "supplier_reply") {
        return true;
      }
      return SUPPLIER_VENDOR_DOMAINS.has(domain);

    case "pagos_admin":
      return matchesPagosAdminPreset(row);

    case "logistica":
      return category === "vendor_logistics" || LOGISTICS_DOMAINS.has(domain);

    case "con_senal_equipo":
      return Boolean(row.equipment_signal?.trim());

    default:
      return true;
  }
}

export function filterWarmCasesByViewPreset(
  items: WarmCaseItem[],
  preset: WarmCaseViewPreset,
): WarmCaseItem[] {
  if (preset === "todo") {
    return items;
  }
  return items.filter((row) => matchesWarmCaseViewPreset(row, preset));
}
