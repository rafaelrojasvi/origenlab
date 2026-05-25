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
  "eppendorf.com",
  "valuenindustrial.com",
  "gzfanbolun.com",
  "yuanhuai.com",
]);

const REAL_CLIENT_DOMAINS: ReadonlySet<string> = new Set(["ceaf.cl"]);

/** Defense-in-depth: rows that must not show under Clientes reales. */
export function isExcludedFromClientesReales(row: WarmCaseItem): boolean {
  const domain = emailDomain(row.contact_email);
  const email = row.contact_email.trim().toLowerCase();
  const hay = [row.contact_email, row.subject, row.snippet].join(" ").toLowerCase();

  if (email === "contacto@origenlab.cl" || domain === "origenlab.cl" || domain === "labdelivery.cl") {
    return true;
  }
  if (domain === "accounts.google.com" || hay.includes("alerta de seguridad")) {
    return true;
  }
  if (SUPPLIER_VENDOR_DOMAINS.has(domain)) {
    return true;
  }
  if (hay.includes("confirm your registration") || hay.includes("please confirm your registration")) {
    return true;
  }
  return false;
}

function matchesRealClientPostSale(row: WarmCaseItem): boolean {
  const domain = emailDomain(row.contact_email);
  if (!REAL_CLIENT_DOMAINS.has(domain)) {
    return false;
  }
  const hay = [row.subject, row.snippet].join(" ").toLowerCase();
  return (
    hay.includes("remite oc") ||
    hay.includes("orden de compra") ||
    hay.includes("datos bancarios") ||
    hay.includes("solicita datos banc")
  );
}

const LOGISTICS_DOMAINS: ReadonlySet<string> = new Set(["dhl.com"]);

function haystackIncludesLogistics(row: WarmCaseItem): boolean {
  const hay = [row.subject, row.snippet, row.account_name].join(" ").toLowerCase();
  return (
    hay.includes("dhl") ||
    hay.includes("cuenta importación") ||
    hay.includes("cuenta importacion") ||
    hay.includes("propuesta comercial dhl") ||
    hay.includes("solicitud cuenta")
  );
}

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
  return (
    hay.includes("factura") ||
    hay.includes("transferencia") ||
    hay.includes("datos bancarios") ||
    hay.includes("solicita datos banc")
  );
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
      if (isExcludedFromClientesReales(row)) {
        return false;
      }
      if (CLIENTES_REALES_CATEGORIES.has(category)) {
        return true;
      }
      return category === "waiting_supplier" && matchesRealClientPostSale(row);

    case "proveedores":
      if (category === "vendor_logistics") {
        return false;
      }
      if (category === "supplier_reply") {
        return true;
      }
      if (SUPPLIER_VENDOR_DOMAINS.has(domain)) {
        return true;
      }
      if (isExcludedFromClientesReales(row) && category === "client_reply") {
        return true;
      }
      return false;

    case "pagos_admin":
      return matchesPagosAdminPreset(row);

    case "logistica":
      if (category === "vendor_logistics" || LOGISTICS_DOMAINS.has(domain)) {
        return true;
      }
      return (
        haystackIncludesLogistics(row) &&
        category !== "auto_reply" &&
        !isExcludedFromClientesReales(row)
      );

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
