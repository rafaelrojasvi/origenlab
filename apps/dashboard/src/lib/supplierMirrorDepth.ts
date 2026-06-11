import type { GmailInteractionAuditDomainRow } from "../api/gmailInteractionAuditTypes";
import type { WarmCaseItem } from "../api/commercialTypes";

export const SUPPLIER_AUDIT_MISSING_LABEL = "Sin snapshot Gmail publicado";

export function supplierMirrorCaseLabel(caseCount: number): string {
  if (caseCount <= 0) return "Sin casos en espejo";
  return caseCount === 1 ? "1 caso en espejo" : `${caseCount} casos en espejo`;
}

export function supplierGmailDetectedLabel(items: WarmCaseItem[]): string | null {
  const maxGrouped = items.reduce(
    (max, row) => Math.max(max, row.grouped_email_count ?? 1),
    1,
  );
  if (maxGrouped <= 1) return null;
  return `${maxGrouped}+ mensajes Gmail detectados`;
}

export function supplierSqliteAuditLabel(audit: GmailInteractionAuditDomainRow): string {
  const threadLabel = audit.thread_count === 1 ? "1 hilo" : `${audit.thread_count} hilos`;
  return `${audit.message_count} mensajes SQLite/Gmail · ${threadLabel}`;
}

export function supplierAuditDetailLabel(audit: GmailInteractionAuditDomainRow): string {
  const threadLabel = audit.thread_count === 1 ? "1 hilo" : `${audit.thread_count} hilos`;
  return (
    `Historial detectado en SQLite: ${audit.message_count} mensajes · ` +
    `${audit.sent_count} enviados · ${audit.received_count} recibidos · ${threadLabel}`
  );
}

export function buildSupplierMirrorDepthSummary(
  items: WarmCaseItem[],
  audit?: GmailInteractionAuditDomainRow | null,
): string {
  const mirror = supplierMirrorCaseLabel(items.length);
  if (audit) {
    return `${mirror} · ${supplierSqliteAuditLabel(audit)}`;
  }
  const gmail = supplierGmailDetectedLabel(items);
  return gmail ? `${mirror} · ${gmail}` : mirror;
}
