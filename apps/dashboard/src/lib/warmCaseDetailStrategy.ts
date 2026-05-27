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

/** Redact URLs, IDs, and bank-like fragments from operator previews. */
export function sanitizeOperatorPreview(text: string, maxLen = 280): string {
  let cleaned = safePreviewText(text, maxLen + 40);
  for (const pattern of SENSITIVE_PATTERNS) {
    cleaned = cleaned.replace(pattern, "[redacted]");
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
    case "internal_admin":
    case "system_noise":
    case "bounce_problem":
    case "bounce":
    case "auto_reply":
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
          "Supplier pricing or availability arrived. Tie it to the active client opportunity before quoting.",
        strategy:
          "Link this supplier price to the matching client opportunity. Confirm specs, margin, shipping, and lead time. Prepare the client quote only after numbers are reconciled — do not send from the dashboard.",
      };
    case "supplier_followup":
    case "supplier_reply":
      return {
        summary: "Supplier thread needs a read and reconciliation with the client side.",
        strategy:
          "Read the supplier response, close any missing technical or commercial gaps, and update the client quote or internal notes. Keep supplier traffic out of the client inbox view.",
      };
    case "payment_admin":
    case "payment_received":
      return {
        summary: "Payment or banking admin thread — operational, not a sales quote.",
        strategy:
          "Register or confirm the payment / bank detail in your operational workflow. Link to the commercial deal if one exists. Do not treat this as a quoting thread and do not originate client outreach here.",
      };
    case "logistics_admin":
    case "vendor_logistics":
      return {
        summary: "Logistics / import / carrier admin — unblock freight or account setup.",
        strategy:
          "Resolve the DHL, import account, or freight blocker and link progress to the deal timeline. This is not a client opportunity — keep it in payments & logistics until cleared.",
      };
    case "deal_evidence_candidate":
      return {
        summary: "Thread looks like purchase-order or deal evidence, not a new lead.",
        strategy:
          "Open the commercial deals mirror and align this thread to the existing deal timeline. Do not open a duplicate quote or parallel opportunity.",
      };
    case "client_opportunity":
    case "opportunity":
      return {
        summary: "Client-side opportunity signal — validate before quoting.",
        strategy:
          "Validate specifications, target price band, and supplier availability. Gather supplier quotes if needed, then prepare the client quote offline — read-only here.",
      };
    case "client_response":
    case "client_reply":
      return {
        summary: "Client is waiting on a response or clarification.",
        strategy:
          "Respond to the client with status and any missing specs. Check whether supplier quotes or internal margin review are still open before committing dates.",
      };
    case "quote_sent":
      return {
        summary: "Quote already sent — monitor client follow-up.",
        strategy:
          "Track client reply and supplier lead times. Nudge internally if the quote window is stalling; no resend from this dashboard.",
      };
    case "waiting_supplier":
      return {
        summary: "Ball is with the supplier.",
        strategy:
          "Follow up with the supplier for missing price, lead time, or stock. Update the client only when you have firm numbers.",
      };
    case "waiting_client":
      return {
        summary: "Ball is with the client.",
        strategy:
          "Wait for client confirmation or data. Light follow-up only if the agreed window passed.",
      };
    case "bounce_problem":
    case "bounce":
      return {
        summary: "Delivery problem — fix addressing before outreach.",
        strategy:
          "Verify the contact email and suppression state. Do not retry outreach until the address is confirmed in the pipeline.",
      };
    case "system_noise":
    case "auto_reply":
      return {
        summary: "Automated or low-value noise — no commercial action.",
        strategy:
          "No operator action required unless it masks a real client thread. Keep hidden from client queues.",
      };
    case "internal_admin":
      return {
        summary: "Internal operator note — not client-facing.",
        strategy:
          "Handle in internal admin context only. Do not classify as client response or opportunity.",
      };
    default:
      return {
        summary: "Warm thread needs triage by role category.",
        strategy:
          "Review the role category and move work to the matching sidebar section. All actions remain outside this read-only dashboard.",
      };
  }
}

export function buildWarmCaseDetailView(row: WarmCaseItem): WarmCaseDetailView {
  const category = row.category;
  const { summary, strategy } = strategyForCategory(category);
  const org = row.account_name?.trim() || row.contact_email;
  const subjectBit = row.subject?.trim() ? sanitizeOperatorPreview(row.subject, 72) : "Warm thread";
  const caseTitle = `${org}: ${subjectBit}`;
  const linkedSection = linkedSectionForCategory(category);
  const equipment = row.equipment_signal?.trim()
    ? sanitizeOperatorPreview(row.equipment_signal, 120)
    : "";

  let inferredSummary = summary;
  if (equipment) {
    inferredSummary = `${summary} Equipment signal: ${equipment}.`;
  }
  if (row.status === "problem") {
    inferredSummary = `${inferredSummary} Status flagged as problem — prioritize resolution.`;
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
