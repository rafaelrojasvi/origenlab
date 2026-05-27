/** Human-readable labels for API token strings (read-only display). */

export type OperatorLabelKind =
  | "warm_status"
  | "warm_category"
  | "warm_next_action"
  | "equipment_next_action"
  | "equipment_contact_status"
  | "equipment_safe_channel"
  | "equipment_category";

const WARM_STATUS: Record<string, string> = {
  new: "Nuevo",
  open: "Abierto",
  waiting: "En espera",
  quoted: "Cotizado",
  problem: "Problema",
};

const WARM_CATEGORY: Record<string, string> = {
  client_opportunity: "Oportunidad cliente",
  client_response: "Respuesta cliente",
  supplier_quote_received: "Cotización proveedor",
  supplier_followup: "Seguimiento proveedor",
  logistics_admin: "Logística admin",
  internal_admin: "Admin interno",
  system_noise: "Ruido sistema",
  bounce_problem: "Problema rebote",
  deal_evidence_candidate: "Evidencia deal",
  client_reply: "Respuesta cliente",
  supplier_reply: "Respuesta proveedor",
  quote_sent: "Cotización enviada",
  waiting_supplier: "Esperando proveedor",
  waiting_client: "Esperando cliente",
  bounce: "Rebote",
  opportunity: "Oportunidad",
  auto_reply: "Respuesta automática",
  vendor_logistics: "Logística / proveedor admin",
  payment_admin: "Pago / admin comercial",
  payment_received: "Pago recibido",
};

const WARM_NEXT_ACTION: Record<string, string> = {
  auto_reply: "Ignorar respuesta automática",
  vendor_logistics: "Revisar logística / importación",
  payment_admin: "Registrar / confirmar pago",
  supplier_reply: "Leer propuesta del proveedor",
  client_reply: "Responder hilo comercial",
};

const EQUIPMENT_NEXT_ACTION: Record<string, string> = {
  quote_now: "Cotizar ahora",
  needs_supplier_quote: "Requiere cotización proveedor",
};

const EQUIPMENT_CONTACT_STATUS: Record<string, string> = {
  no_verified_buyer_email: "Sin email verificado",
};

const EQUIPMENT_SAFE_CHANNEL: Record<string, string> = {
  mercado_publico_bid: "Mercado Público",
  supplier_quote_request: "Cotización proveedor",
};

const EQUIPMENT_CATEGORY: Record<string, string> = {
  centrifuge: "Centrífuga",
  balance: "Balanza",
  incubator: "Incubadora",
  lab_ultrasonic_processor: "Procesador ultrasónico",
};

const TABLES: Record<OperatorLabelKind, Record<string, string>> = {
  warm_status: WARM_STATUS,
  warm_category: WARM_CATEGORY,
  warm_next_action: WARM_NEXT_ACTION,
  equipment_next_action: EQUIPMENT_NEXT_ACTION,
  equipment_contact_status: EQUIPMENT_CONTACT_STATUS,
  equipment_safe_channel: EQUIPMENT_SAFE_CHANNEL,
  equipment_category: EQUIPMENT_CATEGORY,
};

function normalizeToken(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, "_");
}

/** Returns display label and raw token for tooltips. */
export function formatOperatorToken(
  raw: string | null | undefined,
  kind: OperatorLabelKind,
): { label: string; raw: string } {
  const token = normalizeToken(raw || "");
  if (!token) {
    return { label: "—", raw: "" };
  }
  const table = TABLES[kind];
  const label = table[token] ?? token.replace(/_/g, " ");
  return { label, raw: token };
}
