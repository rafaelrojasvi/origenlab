/** UI types for GET /mirror/commercial/deals (redacted Postgres mirror). */

export type CommercialDealUiRow = {
  client_org_name: string;
  supplier_org_name: string;
  deal_status: string;
  margin_status: string;
  reconciliation_status: string | null;
  freight_status: string | null;
  client_sale_net_clp: number | null;
  client_sale_gross_clp: number | null;
  client_payment_received_clp: number | null;
  supplier_invoice_total_decimal: string | null;
  supplier_amount_paid_decimal: string | null;
  margin_net_clp: number | null;
  margin_pct: number | null;
  margin_blockers: string[];
  updated_at: string | null;
};

export type CommercialDealsListUi = {
  table_available: boolean;
  items: CommercialDealUiRow[];
  total: number;
  limit: number;
  read_only: boolean;
  data_source: "postgres_mirror";
};
