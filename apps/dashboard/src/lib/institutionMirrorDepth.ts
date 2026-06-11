import type { CustomerInstitutionGroup } from "./customerInstitutionGroups";
import { formatDashboardDateTime } from "./dashboardDateFormat";

export function institutionGmailDetectedCount(group: CustomerInstitutionGroup): number {
  return group.totalGmailSent + group.totalGmailReceived;
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

export function institutionGmailHistorySummary(group: CustomerInstitutionGroup): {
  mirrorLine: string;
  detectedLine: string;
  compactLine: string;
} {
  const mirrorLine = institutionMirrorHistoryLabel(group);
  const detectedLine = institutionGmailDetectedLabel(group);
  const last =
    group.hasGmailHistory && group.latestGmailLastContactedAt
      ? formatDashboardDateTime(group.latestGmailLastContactedAt)
      : null;
  const compactParts = [mirrorLine, detectedLine];
  if (last && last !== "—") {
    compactParts.push(last);
  }
  return {
    mirrorLine,
    detectedLine,
    compactLine:
      !group.hasGmailHistory && institutionGmailDetectedCount(group) === 0
        ? "Sin historial en espejo"
        : compactParts.join(" · "),
  };
}
