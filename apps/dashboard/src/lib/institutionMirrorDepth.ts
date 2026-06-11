import type { GmailInteractionAuditSnapshot } from "../api/gmailInteractionAuditTypes";
import type { CustomerInstitutionGroup } from "./customerInstitutionGroups";
import { formatDashboardDateTime } from "./dashboardDateFormat";
import { sqliteAuditMessageCount } from "./gmailInteractionAuditMatch";

export function institutionGmailDetectedCount(group: CustomerInstitutionGroup): number {
  return group.totalGmailSent + group.totalGmailReceived;
}

export function institutionSqliteAuditLabel(
  snapshot: GmailInteractionAuditSnapshot | null | undefined,
  domain: string | null | undefined,
): string {
  const count = sqliteAuditMessageCount(snapshot, domain);
  if (count <= 0) {
    return "SQLite/Gmail: sin coincidencias publicadas";
  }
  return `SQLite/Gmail: ${count} mensaje${count === 1 ? "" : "s"} detectados`;
}

export function institutionMirrorHistoryLabel(group: CustomerInstitutionGroup): string {
  if (!group.hasGmailHistory) {
    return "Espejo: sin historial publicado";
  }
  return `Espejo: ${group.totalGmailSent} env. / ${group.totalGmailReceived} rec.`;
}

export function institutionGmailDetectedLabel(group: CustomerInstitutionGroup): string {
  const count = institutionGmailDetectedCount(group);
  if (count <= 0) {
    return "Gmail detectado: sin coincidencias";
  }
  return `Gmail detectado: ${count} mensaje${count === 1 ? "" : "s"}`;
}

export function institutionGmailHistorySummary(
  group: CustomerInstitutionGroup,
  auditSnapshot?: GmailInteractionAuditSnapshot | null,
): {
  mirrorLine: string;
  detectedLine: string;
  sqliteLine: string;
  compactLine: string;
} {
  const mirrorLine = institutionMirrorHistoryLabel(group);
  const detectedLine = institutionGmailDetectedLabel(group);
  const sqliteLine = institutionSqliteAuditLabel(auditSnapshot, group.domain);
  const sqliteCount = sqliteAuditMessageCount(auditSnapshot, group.domain);
  const last =
    group.hasGmailHistory && group.latestGmailLastContactedAt
      ? formatDashboardDateTime(group.latestGmailLastContactedAt)
      : null;
  const compactParts = [mirrorLine, detectedLine, sqliteLine];
  if (last && last !== "—") {
    compactParts.push(last);
  }
  return {
    mirrorLine,
    detectedLine,
    sqliteLine,
    compactLine:
      !group.hasGmailHistory &&
      institutionGmailDetectedCount(group) === 0 &&
      sqliteCount === 0
        ? "Sin historial en espejo"
        : compactParts.join(" · "),
  };
}
