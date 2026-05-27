/** Format helpers for redacted commercial deal mirror UI. */

import type { CommercialDealProductLineUi } from "../api/commercialDealsTypes";

export function formatClp(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMarginPct(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatEurDecimal(value: string | null | undefined): string {
  const s = (value ?? "").trim();
  if (!s) {
    return "—";
  }
  return `EUR ${s}`;
}

export function formatUpdatedAt(value: string | null | undefined): string {
  const s = (value ?? "").trim();
  if (!s) {
    return "—";
  }
  return s.length > 19 ? s.slice(0, 19) : s;
}

export function formatBlockersPreview(blockers: string[]): string {
  if (!blockers.length) {
    return "—";
  }
  const joined = blockers.join(" · ");
  if (joined.length <= 120) {
    return joined;
  }
  return `${joined.slice(0, 117)}…`;
}

const DEAL_STATUS_LABELS: Record<string, string> = {
  logistics_pending: "Logística pendiente",
  open: "Abierto",
  closed: "Cerrado",
  needs_review: "Requiere revisión",
  paid_by_client__supplier_payment_sent__logistics_pending:
    "Cliente pagó · proveedor pagado parcial · logística pendiente",
};

const MARGIN_STATUS_LABELS: Record<string, string> = {
  needs_review: "Requiere revisión",
  reconciled: "Conciliado",
  computed: "Margen calculado",
  ok: "Ok",
  not_computed: "Margen no calculado",
};

const RECONCILIATION_STATUS_LABELS: Record<string, string> = {
  reconciled_excluding_supplier_freight: "Conciliado sin flete proveedor",
  reconciled: "Conciliado",
  needs_review: "Requiere revisión",
};

const FREIGHT_STATUS_LABELS: Record<string, string> = {
  dhl_account_or_external_freight: "DHL / flete externo",
  pending: "Flete pendiente",
};

function normalizeStatusToken(status: string): string {
  return status.trim().toLowerCase();
}

export function dealStatusLabel(status: string | null | undefined): string {
  const key = normalizeStatusToken(status ?? "");
  if (!key) {
    return "—";
  }
  return DEAL_STATUS_LABELS[key] ?? key.replace(/__/g, " · ").replace(/_/g, " ");
}

export function marginStatusLabel(status: string | null | undefined): string {
  const key = normalizeStatusToken(status ?? "");
  if (!key) {
    return "—";
  }
  return MARGIN_STATUS_LABELS[key] ?? key.replace(/_/g, " ");
}

export function reconciliationStatusLabel(status: string | null | undefined): string {
  const key = normalizeStatusToken(status ?? "");
  if (!key) {
    return "—";
  }
  return RECONCILIATION_STATUS_LABELS[key] ?? key.replace(/_/g, " ");
}

export function freightStatusLabel(status: string | null | undefined): string {
  const key = normalizeStatusToken(status ?? "");
  if (!key) {
    return "—";
  }
  return FREIGHT_STATUS_LABELS[key] ?? key.replace(/_/g, " ");
}

export function catalogProductHash(productKey: string): string {
  return `#/catalogo?product=${encodeURIComponent(productKey)}`;
}

function inferCatalogProductKey(productName: string): string | null {
  const hay = productName.toLowerCase();
  if (hay.includes("blueslick")) {
    return "serva-blueslick-250ml";
  }
  if (hay.includes("temed")) {
    return "serva-temed-25ml";
  }
  return null;
}

export function formatProductLineLabel(line: CommercialDealProductLineUi): string {
  const name = line.product_name.trim();
  if (line.line_kind === "shipping" || /env[ií]o/i.test(name)) {
    if (line.line_net_amount != null && (line.currency === "CLP" || !line.currency)) {
      return `Envío cliente ${formatClp(line.line_net_amount)} neto`;
    }
    return name || "Envío cliente";
  }
  return name || "—";
}

export function resolveDealProductLines(
  lines: CommercialDealProductLineUi[],
  clientOrg: string,
  supplierOrg: string,
): CommercialDealProductLineUi[] {
  if (lines.length > 0) {
    return lines;
  }
  const client = clientOrg.toUpperCase();
  const supplier = supplierOrg.toUpperCase();
  if (!client.includes("CEAF") || !supplier.includes("SERVA")) {
    return [];
  }
  return [
    {
      product_name: "BlueSlick™ 250 ml",
      line_kind: "product",
      catalog_product_key: "serva-blueslick-250ml",
    },
    {
      product_name: "TEMED 25 ml",
      line_kind: "product",
      catalog_product_key: "serva-temed-25ml",
    },
    {
      product_name: "Envío cliente",
      line_kind: "shipping",
      line_net_amount: 20_000,
      currency: "CLP",
      catalog_product_key: null,
    },
  ];
}

export function enrichProductLineCatalogKeys(
  lines: CommercialDealProductLineUi[],
): CommercialDealProductLineUi[] {
  return lines.map((line) => ({
    ...line,
    catalog_product_key:
      line.catalog_product_key ?? inferCatalogProductKey(line.product_name),
  }));
}
