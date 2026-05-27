/** Warm-case row display helpers (subject lines, grouping). */

import type { WarmCaseItem } from "../api/commercialTypes";
import { emailDomain } from "./clientTableView";
import { truncate } from "./safeText";

function isCrtopSupplierRow(row: WarmCaseItem): boolean {
  const domain = emailDomain(row.contact_email);
  const account = (row.account_name || "").trim().toUpperCase();
  const subject = (row.subject || "").toLowerCase();
  return (
    domain === "crtopmachine.com" ||
    account === "CRTOP" ||
    subject.includes("crtop") ||
    subject.includes("reactor") ||
    subject.includes("olt-hp")
  );
}

function crtopProductLabel(row: WarmCaseItem): string {
  const signal = (row.equipment_signal || "").toLowerCase();
  if (signal.includes("reactor") || signal === "reactor") {
    return "Reactor OLT-HP-5L";
  }
  const sub = (row.subject || "").toLowerCase();
  if (sub.includes("olt-hp") || sub.includes("olt hp")) {
    return "Reactor OLT-HP-5L";
  }
  if (sub.includes("reactor")) {
    return "Reactor OLT-HP-5L";
  }
  return "Reactor (cotización)";
}

/**
 * Primary subject column text. For grouped CRTOP threads, show vendor + product + ×N
 * (email count in thread, not order quantity).
 */
export function formatWarmCaseSubjectLine(row: WarmCaseItem): string {
  const grouped = row.grouped_email_count ?? 1;
  if (isCrtopSupplierRow(row)) {
    const base = `CRTOP — ${crtopProductLabel(row)}`;
    return grouped > 1 ? `${base} ×${grouped}` : base;
  }
  return row.subject ? truncate(row.subject, 80) : "—";
}

export function warmCaseSubjectShowsInlineGroupCount(row: WarmCaseItem): boolean {
  return isCrtopSupplierRow(row) && (row.grouped_email_count ?? 1) > 1;
}
