import type { WarmCaseCategory, WarmCaseItem } from "../api/commercialTypes";
import type { DashboardSection } from "./dashboardNav";
import { dashboardSectionLabel } from "./dashboardNav";
import { formatOperatorToken } from "./operatorLabels";
import { safePreviewText, truncate } from "./safeText";

export interface WarmCaseDetailView {
  caseTitle: string;
  categoryLabel: string;
  category: WarmCaseCategory;
  statusLabel: string;
  inferredSummary: string;
  recommendedStrategy: string;
  nextActionLabel: string;
  linkedSection: DashboardSection | null;
  linkedSectionLabel: string | null;
  safeSubject: string;
  safeSnippet: string;
  equipmentSignal: string;
}

const SENSITIVE_PATTERNS: RegExp[] = [
  /https?:\/\/[^\s]+/gi,
  /mailto:[^\s]+/gi,
  /gmail\.com\/[^\s]+/gi,
  /\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b/g,
  /\b\d{10,}\b/g,
  /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g,
  /\bcuenta\s*(?:corriente|n[°ºo]\s*\d+)/gi,
  /\b(?:rut|beneficiario|titular)\s*[:#]?\s*[\d.\-kK]+/gi,
];

/** Oculta URLs, IDs y datos bancarios en vistas previas. */
export function sanitizeOperatorPreview(text: string, maxLen = 280): string {
  let cleaned = safePreviewText(text, maxLen + 40);
  for (const pattern of SENSITIVE_PATTERNS) {
    cleaned = cleaned.replace(pattern, "[oculto]");
  }
  return truncate(cleaned.trim(), maxLen);
}

function linkedSectionForCategory(category: WarmCaseCategory): DashboardSection | null {
  switch (category) {
    case "supplier_quote_received":
    case "supplier_followup":
    case "supplier_reply":
      return "suppliers";
    case "payment_admin":
    case "payment_received":
    case "logistics_admin":
    case "vendor_logistics":
      return "payments-logistics";
    case "deal_evidence_candidate":
      return "deals";
    case "client_opportunity":
    case "opportunity":
      return "opportunities";
    case "client_response":
    case "client_reply":
    case "quote_sent":
    case "waiting_client":
    case "waiting_supplier":
      return "inbox";
    default:
      return "inbox";
  }
}

function strategyForCategory(category: WarmCaseCategory): { summary: string; strategy: string } {
  switch (category) {
    case "supplier_quote_received":
      return {
        summary:
          "Llegó un precio o disponibilidad del proveedor. Conéctalo con la oportunidad de cliente activa antes de cotizar.",
        strategy:
          "Relaciona este precio con la oportunidad de cliente correspondiente. Confirma especificaciones, margen, flete y plazo. Prepara la cotización al cliente solo cuando los números estén claros — no se envía correo desde este panel.",
      };
    case "supplier_followup":
    case "supplier_reply":
      return {
        summary: "El proveedor respondió y hay que leer y cuadrar con el lado cliente.",
        strategy:
          "Lee la respuesta del proveedor, cierra datos técnicos o comerciales faltantes y actualiza la cotización o notas internas. Mantén este hilo fuera de la vista de clientes.",
      };
    case "payment_admin":
    case "payment_received":
      return {
        summary: "Hilo de pago o datos bancarios — operativo, no es una cotización comercial.",
        strategy:
          "Registra o confirma el pago en tu flujo operativo. Si existe, vincúlalo al negocio comercial. No uses este hilo para cotizar ni para contactar al cliente.",
      };
    case "logistics_admin":
    case "vendor_logistics":
      return {
        summary: "Logística, importación o transporte — desbloquear flete o cuenta.",
        strategy:
          "Resuelve el bloqueo con DHL, cuenta de importación o flete y registra el avance en la línea de tiempo del negocio. No es una oportunidad de venta.",
      };
    case "deal_evidence_candidate":
      return {
        summary: "Parece orden de compra o evidencia de un negocio ya en curso, no un lead nuevo.",
        strategy:
          "Abre Negocios y alinea este hilo con el negocio existente. No abras una cotización duplicada ni una oportunidad paralela.",
      };
    case "client_opportunity":
    case "opportunity":
      return {
        summary: "Señal de oportunidad del lado cliente — validar antes de cotizar.",
        strategy:
          "Valida especificaciones, rango de precio y disponibilidad de proveedor. Pide cotizaciones a proveedores si hace falta y prepara la oferta al cliente fuera de este panel.",
      };
    case "client_response":
    case "client_reply":
      return {
        summary: "El cliente espera respuesta o aclaración.",
        strategy:
          "Responde con estado y datos que falten. Revisa si aún hay cotizaciones de proveedor o revisión de margen antes de comprometer plazos.",
      };
    case "quote_sent":
      return {
        summary: "La cotización ya se envió — monitorear respuesta del cliente.",
        strategy:
          "Sigue la respuesta del cliente y los plazos del proveedor. Si se estanca el plazo acordado, coordina internamente — no reenvíes desde aquí.",
      };
    case "waiting_supplier":
      return {
        summary: "La pelota está con el proveedor.",
        strategy:
          "Insiste al proveedor por precio, plazo o stock faltante. Avisa al cliente solo con números firmes.",
      };
    case "waiting_client":
      return {
        summary: "La pelota está con el cliente.",
        strategy:
          "Espera confirmación o datos del cliente. Seguimiento suave solo si pasó el plazo acordado.",
      };
    case "bounce_problem":
    case "bounce":
      return {
        summary: "Problema de entrega — corregir dirección antes de insistir.",
        strategy:
          "Verifica el correo y el estado de supresión en el pipeline. No reintentes contacto hasta confirmar la dirección.",
      };
    case "system_noise":
    case "auto_reply":
      return {
        summary: "Ruido automático o de bajo valor — sin acción comercial.",
        strategy:
          "No requiere acción salvo que oculte un hilo real de cliente. Mantén fuera de las colas de clientes.",
      };
    case "internal_admin":
      return {
        summary: "Nota interna de operación — no es frente al cliente.",
        strategy:
          "Trátalo solo como administración interna. No lo clasifiques como respuesta u oportunidad de cliente.",
      };
    default:
      return {
        summary: "Hilo tibio que requiere clasificación por rol.",
        strategy:
          "Revisa la categoría y muévelo a la sección correcta del menú. Todas las acciones quedan fuera de este panel de solo lectura.",
      };
  }
}

function strategyOverrideForKnownCases(
  row: WarmCaseItem,
): { summary: string; strategy: string } | null {
  const subject = (row.subject || "").toLowerCase();
  const sender = (row.contact_email || "").toLowerCase();
  if ((subject.includes("rv10.70") || subject.includes("3812200")) && subject.includes("rg energia")) {
    return {
      summary:
        "Cliente solicita 3 tubos de vapor IKA RV10.70. Proveedor IKA respondió precio 112,00 y stock disponible. Falta confirmar moneda y despacho.",
      strategy:
        "Confirma moneda de la cotización, plazo de importación y condiciones de despacho a San Bernardo. Luego calcula margen y prepara la cotización al cliente fuera de este panel.",
    };
  }
  if (
    sender.includes("crtopmachine.com") ||
    subject.includes("crtop") ||
    subject.includes("olt-hp-5l") ||
    subject.includes("inquiry about our reactor")
  ) {
    return {
      summary:
        "Proveedor CRTOP envió cotización de reactor OLT-HP-5L por US$10,600 EXW. Falta shipping y costos de importación antes de cotizar al cliente.",
      strategy:
        "Confirma dirección de envío, costo logístico, peso/dimensiones, HS code y garantía/certificados/manual. Con esos datos calcula costo aterrizado y margen antes de responder.",
    };
  }
  return null;
}

export function buildWarmCaseDetailView(row: WarmCaseItem): WarmCaseDetailView {
  const category = row.category;
  const base = strategyForCategory(category);
  const override = strategyOverrideForKnownCases(row);
  const { summary, strategy } = override ?? base;
  const org = row.account_name?.trim() || row.contact_email;
  const subjectBit = row.subject?.trim() ? sanitizeOperatorPreview(row.subject, 72) : "Hilo tibio";
  const caseTitle = `${org}: ${subjectBit}`;
  const linkedSection = linkedSectionForCategory(category);
  const equipment = row.equipment_signal?.trim()
    ? sanitizeOperatorPreview(row.equipment_signal, 120)
    : "";

  let inferredSummary = summary;
  if (equipment) {
    inferredSummary = `${summary} Señal de equipo: ${equipment}.`;
  }
  if (row.status === "problem") {
    inferredSummary = `${inferredSummary} Estado marcado como problema — priorizar resolución.`;
  }

  return {
    caseTitle,
    categoryLabel: formatOperatorToken(category, "warm_category").label,
    category,
    statusLabel: formatOperatorToken(row.status, "warm_status").label,
    inferredSummary,
    recommendedStrategy: strategy,
    nextActionLabel: formatOperatorToken(row.next_action, "warm_next_action").label,
    linkedSection,
    linkedSectionLabel: linkedSection ? dashboardSectionLabel(linkedSection) : null,
    safeSubject: row.subject ? sanitizeOperatorPreview(row.subject, 160) : "—",
    safeSnippet: row.snippet ? sanitizeOperatorPreview(row.snippet, 200) : "",
    equipmentSignal: equipment || "—",
  };
}
