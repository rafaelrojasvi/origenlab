/** UI types for read-only catalog mirror (GET /mirror/catalog/products). */

export interface CatalogProductListItemUi {
  product_key: string;
  display_name: string;
  brand: string | null;
  product_kind: string;
  equipment_class: string | null;
  model_number: string | null;
  public_summary: string | null;
  confidence: string;
}

export interface CatalogProductAliasUi {
  alias_source: string;
  alias_code: string;
  alias_kind: string | null;
}

export interface CatalogProductCategoryUi {
  category_key: string;
  display_name: string;
  equipment_class: string | null;
  is_primary: boolean;
}

export interface CatalogProductSpecUi {
  spec_group: string | null;
  spec_key: string;
  spec_value: string;
  spec_value_numeric: number | null;
  spec_unit: string | null;
  source: string;
  confidence: string;
}

export interface CatalogSupplierOfferUi {
  offer_key: string;
  supplier_org_name: string | null;
  supplier_domain: string | null;
  offer_status: string;
  quoted_at: string | null;
  valid_until: string | null;
  incoterm: string | null;
  payment_terms: string | null;
  delivery_terms: string | null;
  currency: string | null;
  quantity_offered: string | null;
  availability_note: string | null;
  confidence: string;
}

export interface CatalogPriceSnapshotUi {
  snapshot_key: string;
  snapshot_kind: string;
  offer_key: string | null;
  currency: string | null;
  amount_decimal: string | null;
  amount_minor: number | null;
  amount_clp_integer: number | null;
  quantity: string | null;
  unit: string | null;
  incoterm: string | null;
  price_notes: string | null;
  is_public_safe: boolean;
  confidence: string;
  observed_at: string | null;
}

export interface CatalogCommercialLinkUi {
  link_kind: string;
  link_ref: string;
  confidence: string;
}

export interface CatalogProductCommercialHistoryUi {
  history_key: string;
  deal_key: string;
  deal_label: string;
  client_org_name: string | null;
  supplier_org_name: string | null;
  line_side: string;
  line_kind: string;
  quantity: string | null;
  unit: string | null;
  currency: string | null;
  amount_net_clp: number | null;
  amount_decimal: string | null;
  amount_minor: number | null;
  unit_price_decimal: string | null;
  total_price_decimal: string | null;
  margin_status: string | null;
  deal_status: string | null;
  is_public_safe: boolean;
  source_summary: string | null;
  confidence: string;
}

export interface CatalogProductDetailUi {
  product_key: string;
  display_name: string;
  brand: string | null;
  manufacturer_name: string | null;
  product_kind: string;
  equipment_class: string | null;
  model_number: string | null;
  default_unit: string | null;
  website_slug: string | null;
  website_product_id: string | null;
  public_summary: string | null;
  is_active: boolean;
  confidence: string;
  aliases: CatalogProductAliasUi[];
  categories: CatalogProductCategoryUi[];
  specs: CatalogProductSpecUi[];
  supplier_offers: CatalogSupplierOfferUi[];
  price_snapshots: CatalogPriceSnapshotUi[];
  commercial_links: CatalogCommercialLinkUi[];
  commercial_history: CatalogProductCommercialHistoryUi[];
}

export interface CatalogProductsListUi {
  table_available: boolean;
  items: CatalogProductListItemUi[];
  total: number;
  limit: number;
  data_source: "postgres_mirror";
  read_only: boolean;
  disclaimer: string;
}

export interface CatalogProductDetailResponseUi {
  table_available: boolean;
  product: CatalogProductDetailUi | null;
  data_source: "postgres_mirror";
  read_only: boolean;
  disclaimer: string;
}

export interface CatalogListQuery {
  q?: string;
  brand?: string;
  equipment_class?: string;
  category_key?: string;
  limit?: number;
}
