import { describe, expect, it } from "vitest";
import type { CustomerInstitutionGroup } from "./customerInstitutionGroups";
import { institutionGmailHistorySummary } from "./institutionMirrorDepth";

function group(partial: Partial<CustomerInstitutionGroup>): CustomerInstitutionGroup {
  return {
    key: "u",
    institutionName: "Universidad de Chile",
    domain: "uchile.cl",
    sectors: [],
    regions: [],
    buyerTypes: [],
    contactsWithEmail: 1,
    contactsMissingEmail: 0,
    totalRows: 1,
    maxFinalScore: 80,
    anyBlocked: false,
    anyRisk: false,
    hasGmailHistory: false,
    totalGmailSent: 0,
    totalGmailReceived: 0,
    latestGmailLastContactedAt: null,
    latestSafeSubject: null,
    campaignBuckets: [],
    sourceTypes: [],
    rows: [],
    recommendedNextAction: "",
    ...partial,
  };
}

describe("institutionMirrorDepth", () => {
  it("separates espejo vs Gmail detectado", () => {
    const summary = institutionGmailHistorySummary(
      group({
        hasGmailHistory: true,
        totalGmailSent: 3,
        totalGmailReceived: 2,
        latestGmailLastContactedAt: "2026-06-10T13:38:54+00:00",
      }),
    );
    expect(summary.mirrorLine).toBe("Espejo: 3 env. / 2 rec.");
    expect(summary.detectedLine).toBe("Gmail detectado: 5 mensajes");
    expect(summary.compactLine).toMatch(/Espejo:/);
    expect(summary.compactLine).toMatch(/Gmail detectado:/);
  });

  it("shows sin historial en espejo when no mirror match", () => {
    const summary = institutionGmailHistorySummary(group({}));
    expect(summary.compactLine).toBe("Sin historial en espejo");
    expect(summary.detectedLine).toBe("Gmail detectado: sin coincidencias");
  });
});
