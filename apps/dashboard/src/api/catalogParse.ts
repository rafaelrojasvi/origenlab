/**
 * Parse redacted catalog mirror responses.
 * Drops private fields and redacts forbidden values even if the API returns them.
 */

import type {
  CatalogCommercialLinkUi,
  CatalogProductCommercialHistoryUi,
  CatalogPriceSnapshotUi,
  CatalogProductAliasUi,
  CatalogProductCategoryUi,
  CatalogProductDetailResponseUi,
  CatalogProductDetailUi,
  CatalogProductListItemUi,
  CatalogProductSpecUi,
  CatalogProductsListUi,
  CatalogSupplierOfferUi,
} from "./catalogTypes";
import { safePreviewText, safeStr } from "../lib/safeText";

export const CATALOG_FORBIDDEN_KEYS = new Set([
  "gmail_url",
  "evidence_email_id",
  "evidence_attachment_id",
  "source_file",
  "source_path",
  "source_preview_path",
  "body",
  "email_body",
  "full_text",
  "extract_snippet",
  "transfer_id",
  "operation_id",
  "notes",
]);

export const CATALOG_FORBIDDEN_PROSE_ARTIFACTS = [
  "cotizacióny",
  "porcliente",
  "cantidad3",
  "antesde",
  "decotizar",
  "montoes",
  "Monto112",
  "vaporIKA",
  "decalentamiento",
  "espejoPostgres",
  "lafuente",
  "cuerpos decorreo",
  "oportunida de s",
  "enelectroforesis",
] as const;

const DISPLAY_PROSE_REPAIRS: [RegExp, string][] = [[/enelectroforesis/gi, "en electroforesis"]];

const FORBIDDEN_VALUE_PATTERNS: RegExp[] = [
  /\bbank\b/i,
  /\bbanco\b/i,
  /\bswift\b/i,
  /\biban\b/i,
  /\bcuenta\b/i,
  /\bbeneficiario\b/i,
  /\brut\b/i,
  /gmail\.com/i,
  /mail\.google/i,
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stripForbiddenKeys(row: Record<string, unknown>): void {
  for (const key of Object.keys(row)) {
    if (CATALOG_FORBIDDEN_KEYS.has(key)) {
      delete row[key];
    }
  }
}

function repairCatalogDisplayProse(text: string): string {
  let out = text;
  for (const [pattern, replacement] of DISPLAY_PROSE_REPAIRS) {
    out = out.replace(pattern, replacement);
  }
  return out;
}

function sanitizeCatalogText(value: unknown, maxLen = 2000): string {
  const text = safePreviewText(value, maxLen);
  if (!text) {
    return "";
  }
  for (const pattern of FORBIDDEN_VALUE_PATTERNS) {
    if (pattern.test(text)) {
      return "";
    }
  }
  return repairCatalogDisplayProse(text);
}

function optionalStr(value: unknown, maxLen = 500): string | null {
  const text = sanitizeCatalogText(value, maxLen);
  return text || null;
}

function optionalBool(value: unknown): boolean {
  return Boolean(value);
}

function optionalNum(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

export function parseCatalogProductListItem(raw: unknown, index: number): CatalogProductListItemUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    product_key: sanitizeCatalogText(r.product_key, 120) || `product-${index + 1}`,
    display_name: sanitizeCatalogText(r.display_name, 300) || "Producto sin nombre",
    brand: optionalStr(r.brand, 120),
    product_kind: sanitizeCatalogText(r.product_kind, 80) || "unknown",
    equipment_class: optionalStr(r.equipment_class, 80),
    model_number: optionalStr(r.model_number, 120),
    public_summary: optionalStr(r.public_summary, 1200),
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
  };
}

export function parseCatalogProductAlias(raw: unknown): CatalogProductAliasUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    alias_source: sanitizeCatalogText(r.alias_source, 80) || "unknown",
    alias_code: safeStr(r.alias_code).trim(),
    alias_kind: optionalStr(r.alias_kind, 80),
  };
}

export function parseCatalogProductCategory(raw: unknown): CatalogProductCategoryUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    category_key: sanitizeCatalogText(r.category_key, 120) || "unknown",
    display_name: sanitizeCatalogText(r.display_name, 200) || "—",
    equipment_class: optionalStr(r.equipment_class, 80),
    is_primary: optionalBool(r.is_primary),
  };
}

export function parseCatalogProductSpec(raw: unknown): CatalogProductSpecUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    spec_group: optionalStr(r.spec_group, 80),
    spec_key: sanitizeCatalogText(r.spec_key, 120) || "spec",
    spec_value: sanitizeCatalogText(r.spec_value, 400) || "—",
    spec_value_numeric: optionalNum(r.spec_value_numeric),
    spec_unit: optionalStr(r.spec_unit, 40),
    source: sanitizeCatalogText(r.source, 80) || "unknown",
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
  };
}

export function parseCatalogSupplierOffer(raw: unknown): CatalogSupplierOfferUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    offer_key: sanitizeCatalogText(r.offer_key, 120) || "offer",
    supplier_org_name: optionalStr(r.supplier_org_name, 200),
    supplier_domain: optionalStr(r.supplier_domain, 120),
    offer_status: sanitizeCatalogText(r.offer_status, 80) || "unknown",
    quoted_at: optionalStr(r.quoted_at, 40),
    valid_until: optionalStr(r.valid_until, 80),
    incoterm: optionalStr(r.incoterm, 40),
    payment_terms: optionalStr(r.payment_terms, 400),
    delivery_terms: optionalStr(r.delivery_terms, 400),
    currency: optionalStr(r.currency, 12),
    quantity_offered: optionalStr(r.quantity_offered, 40),
    availability_note: optionalStr(r.availability_note, 800),
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
  };
}

export function parseCatalogPriceSnapshot(raw: unknown): CatalogPriceSnapshotUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    snapshot_key: sanitizeCatalogText(r.snapshot_key, 120) || "snapshot",
    snapshot_kind: sanitizeCatalogText(r.snapshot_kind, 80) || "supplier_quote",
    offer_key: optionalStr(r.offer_key, 120),
    currency: optionalStr(r.currency, 12),
    amount_decimal: optionalStr(r.amount_decimal, 40),
    amount_minor: optionalNum(r.amount_minor),
    amount_clp_integer: optionalNum(r.amount_clp_integer),
    quantity: optionalStr(r.quantity, 40),
    unit: optionalStr(r.unit, 40),
    incoterm: optionalStr(r.incoterm, 40),
    price_notes: optionalStr(r.price_notes, 1200),
    is_public_safe: optionalBool(r.is_public_safe),
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
    observed_at: optionalStr(r.observed_at, 40),
  };
}

export function parseCatalogCommercialLink(raw: unknown): CatalogCommercialLinkUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    link_kind: sanitizeCatalogText(r.link_kind, 80) || "unknown",
    link_ref: sanitizeCatalogText(r.link_ref, 200) || "—",
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
  };
}

export function parseCatalogCommercialHistory(
  raw: unknown,
): CatalogProductCommercialHistoryUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  return {
    history_key: sanitizeCatalogText(r.history_key, 160) || "history",
    deal_key: sanitizeCatalogText(r.deal_key, 120) || "deal",
    deal_label: sanitizeCatalogText(r.deal_label, 120) || "Negocio",
    client_org_name: optionalStr(r.client_org_name, 120),
    supplier_org_name: optionalStr(r.supplier_org_name, 160),
    line_side: sanitizeCatalogText(r.line_side, 20) || "client",
    line_kind: sanitizeCatalogText(r.line_kind, 40) || "product",
    quantity: optionalStr(r.quantity, 40),
    unit: optionalStr(r.unit, 40),
    currency: optionalStr(r.currency, 12),
    amount_net_clp: optionalNum(r.amount_net_clp),
    amount_decimal: optionalStr(r.amount_decimal, 40),
    amount_minor: optionalNum(r.amount_minor),
    unit_price_decimal: optionalStr(r.unit_price_decimal, 40),
    total_price_decimal: optionalStr(r.total_price_decimal, 40),
    margin_status: optionalStr(r.margin_status, 80),
    deal_status: optionalStr(r.deal_status, 120),
    is_public_safe: optionalBool(r.is_public_safe),
    source_summary: optionalStr(r.source_summary, 300),
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
  };
}

export function parseCatalogProductDetail(raw: unknown): CatalogProductDetailUi {
  const r = asRecord(raw);
  stripForbiddenKeys(r);
  const aliases = Array.isArray(r.aliases) ? r.aliases.map(parseCatalogProductAlias) : [];
  const categories = Array.isArray(r.categories) ? r.categories.map(parseCatalogProductCategory) : [];
  const specs = Array.isArray(r.specs) ? r.specs.map(parseCatalogProductSpec) : [];
  const supplier_offers = Array.isArray(r.supplier_offers)
    ? r.supplier_offers.map(parseCatalogSupplierOffer)
    : [];
  const price_snapshots = Array.isArray(r.price_snapshots)
    ? r.price_snapshots.map(parseCatalogPriceSnapshot)
    : [];
  const commercial_links = Array.isArray(r.commercial_links)
    ? r.commercial_links.map(parseCatalogCommercialLink)
    : [];
  const commercial_history = Array.isArray(r.commercial_history)
    ? r.commercial_history.map(parseCatalogCommercialHistory)
    : [];

  return {
    product_key: sanitizeCatalogText(r.product_key, 120) || "unknown",
    display_name: sanitizeCatalogText(r.display_name, 300) || "Producto sin nombre",
    brand: optionalStr(r.brand, 120),
    manufacturer_name: optionalStr(r.manufacturer_name, 200),
    product_kind: sanitizeCatalogText(r.product_kind, 80) || "unknown",
    equipment_class: optionalStr(r.equipment_class, 80),
    model_number: optionalStr(r.model_number, 120),
    default_unit: optionalStr(r.default_unit, 40),
    website_slug: optionalStr(r.website_slug, 120),
    website_product_id: optionalStr(r.website_product_id, 120),
    public_summary: optionalStr(r.public_summary, 2000),
    is_active: r.is_active !== false,
    confidence: sanitizeCatalogText(r.confidence, 80) || "unknown",
    aliases,
    categories,
    specs,
    supplier_offers,
    price_snapshots,
    commercial_links,
    commercial_history,
  };
}

export function parseCatalogProductsListResponse(raw: unknown): CatalogProductsListUi {
  const root = asRecord(raw);
  stripForbiddenKeys(root);
  const itemsRaw = Array.isArray(root.items) ? root.items : [];
  return {
    table_available: Boolean(root.table_available),
    items: itemsRaw.map((item, index) => parseCatalogProductListItem(item, index)),
    total: typeof root.total === "number" && Number.isFinite(root.total) ? root.total : itemsRaw.length,
    limit: typeof root.limit === "number" && Number.isFinite(root.limit) ? root.limit : 50,
    data_source: "postgres_mirror",
    read_only: root.read_only !== false,
    disclaimer: sanitizeCatalogText(root.disclaimer, 1200) || "",
  };
}

export function parseCatalogProductDetailResponse(raw: unknown): CatalogProductDetailResponseUi {
  const root = asRecord(raw);
  stripForbiddenKeys(root);
  const productRaw = root.product;
  return {
    table_available: Boolean(root.table_available),
    product:
      productRaw && typeof productRaw === "object" ? parseCatalogProductDetail(productRaw) : null,
    data_source: "postgres_mirror",
    read_only: root.read_only !== false,
    disclaimer: sanitizeCatalogText(root.disclaimer, 1200) || "",
  };
}
