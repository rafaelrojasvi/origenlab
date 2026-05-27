/**
 * Parse redacted commercial deal mirror responses.
 * Drops private fields even if the API returns them.
 */

import type {
  CommercialDealProductLineUi,
  CommercialDealUiRow,
  CommercialDealsListUi,
} from "./commercialDealsTypes";
import { safePreviewText, safeStr } from "../lib/safeText";

const FORBIDDEN_ROW_KEYS = new Set([
  "deal_key",
  "transfer_id",
  "operation_id",
  "source_preview_path",
  "source_preview_sha256",
  "notes_json",
  "operator_private_json",
  "legacy_purchase_event_id",
  "client_contact_email",
  "supplier_contact_email",
  "client_domain",
  "supplier_domain",
  "client_po_number",
  "client_invoice_number",
  "supplier_po_number",
  "extract_snippet",
  "operator_note",
  "gmail_url",
  "source_path",
  "source_file",
  "margin_notes",
  "cost_summaries_by_type",
  "payment_summaries_masked",
]);

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function optionalInt(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  return null;
}

function optionalFloat(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function optionalDecimalString(value: unknown): string | null {
  const s = safeStr(value).trim();
  return s || null;
}

function parseProductLineSummaries(raw: unknown): CommercialDealProductLineUi[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: CommercialDealProductLineUi[] = [];
  for (const item of raw) {
    const r = asRecord(item);
    const product_name = safePreviewText(r.product_name, 120);
    if (!product_name) {
      continue;
    }
    out.push({
      product_name,
      line_kind: safePreviewText(r.line_kind, 40) || "product",
      line_net_amount: optionalInt(r.line_net_amount),
      currency: r.currency == null ? null : safePreviewText(r.currency, 8),
    });
  }
  return out;
}

function parseMarginBlockers(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => safePreviewText(item, 400))
    .filter((text) => text.length > 0);
}

export function parseCommercialDealUiRow(raw: unknown): CommercialDealUiRow {
  const r = asRecord(raw);
  const product_lines = parseProductLineSummaries(r.product_line_summaries);
  for (const key of Object.keys(r)) {
    if (FORBIDDEN_ROW_KEYS.has(key)) {
      delete r[key];
    }
  }
  return {
    client_org_name: safePreviewText(r.client_org_name, 200),
    supplier_org_name: safePreviewText(r.supplier_org_name, 200),
    deal_status: safePreviewText(r.deal_status, 80),
    margin_status: safePreviewText(r.margin_status, 80),
    reconciliation_status: r.reconciliation_status == null ? null : safePreviewText(r.reconciliation_status, 80),
    freight_status: r.freight_status == null ? null : safePreviewText(r.freight_status, 80),
    client_sale_net_clp: optionalInt(r.client_sale_net_clp),
    client_sale_gross_clp: optionalInt(r.client_sale_gross_clp),
    client_payment_received_clp: optionalInt(r.client_payment_received_clp),
    supplier_invoice_total_decimal: optionalDecimalString(r.supplier_invoice_total_decimal),
    supplier_amount_paid_decimal: optionalDecimalString(r.supplier_amount_paid_decimal),
    margin_net_clp: optionalInt(r.margin_net_clp),
    margin_pct: optionalFloat(r.margin_pct),
    margin_blockers: parseMarginBlockers(r.margin_blockers),
    updated_at: r.updated_at == null ? null : safePreviewText(r.updated_at, 40),
    product_lines,
  };
}

export function parseCommercialDealsListResponse(raw: unknown): CommercialDealsListUi {
  const root = asRecord(raw);
  const itemsRaw = Array.isArray(root.items) ? root.items : [];
  return {
    table_available: Boolean(root.table_available),
    items: itemsRaw.map((item) => parseCommercialDealUiRow(item)),
    total: optionalInt(root.total) ?? 0,
    limit: optionalInt(root.limit) ?? 20,
    read_only: root.read_only !== false,
    data_source: "postgres_mirror",
  };
}
