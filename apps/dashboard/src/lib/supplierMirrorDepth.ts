import type { WarmCaseItem } from "../api/commercialTypes";

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

export function buildSupplierMirrorDepthSummary(items: WarmCaseItem[]): string {
  const mirror = supplierMirrorCaseLabel(items.length);
  const gmail = supplierGmailDetectedLabel(items);
  return gmail ? `${mirror} · ${gmail}` : mirror;
}
