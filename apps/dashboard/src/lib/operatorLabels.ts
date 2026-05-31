/** Etiquetas en español para tokens de la API (solo lectura). */

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
  client_opportunity: "Oportunidad de cliente",
  client_response: "Respuesta de cliente",
  supplier_quote_received: "Cotización de proveedor recibida",
  supplier_followup: "Seguimiento de proveedor",
  payment_admin: "Pago / administración",
  logistics_admin: "Logística",
  internal_admin: "Interno / administrativo",
  system_noise: "Sistema / ruido",
  bounce_problem: "Problema de entrega",
  deal_evidence_candidate: "Evidencia de negocio",
  client_reply: "Respuesta de cliente",
  supplier_reply: "Respuesta de proveedor",
  quote_sent: "Cotización enviada",
  waiting_supplier: "Esperando proveedor",
  waiting_client: "Esperando cliente",
  campaign_outreach: "Campaña / outreach",
  waiting_campaign_reply: "Campaña — esperando respuesta",
  auto_acknowledgement: "Acuse automático",
  bounce: "Rebote",
  opportunity: "Oportunidad",
  auto_reply: "Respuesta automática",
  vendor_logistics: "Logística",
  payment_received: "Pago recibido",
};

const WARM_NEXT_ACTION: Record<string, string> = {
  auto_reply: "Ignorar respuesta automática",
  vendor_logistics: "Revisar logística o importación",
  payment_admin: "Registrar o confirmar pago",
  supplier_reply: "Revisar propuesta del proveedor",
  client_reply: "Responder al cliente",
  reply: "Responder",
  wait: "Esperar",
  review: "Revisar",
  follow: "Dar seguimiento",
};

const EQUIPMENT_NEXT_ACTION: Record<string, string> = {
  quote_now: "Cotizar ahora",
  needs_supplier_quote: "Requiere cotización de proveedor",
  monitor: "Monitorear",
};

const EQUIPMENT_CONTACT_STATUS: Record<string, string> = {
  no_verified_buyer_email: "Sin correo verificado del comprador",
  pending: "Pendiente",
};

const EQUIPMENT_SAFE_CHANNEL: Record<string, string> = {
  mercado_publico_bid: "Mercado Público",
  supplier_quote_request: "Cotización a proveedor",
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

/** Etiqueta visible; no expone el token técnico en la UI. */
export function formatOperatorToken(
  raw: string | null | undefined,
  kind: OperatorLabelKind,
): { label: string; raw: string } {
  const token = normalizeToken(raw || "");
  if (!token) {
    return { label: "—", raw: "" };
  }
  const table = TABLES[kind];
  const label = table[token] ?? "Sin clasificar";
  return { label, raw: token };
}
