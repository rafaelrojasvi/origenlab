import { describe, expect, it } from "vitest";

const appSource = import.meta.glob("../App.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
})["../App.tsx"] as string;

const operatorClientSource = import.meta.glob("../api/operatorClient.ts", {
  query: "?raw",
  import: "default",
  eager: true,
})["../api/operatorClient.ts"] as string;

const todayPageSource = import.meta.glob("../pages/TodayPage.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
})["../pages/TodayPage.tsx"] as string;

const commercialMountedSources = Object.entries(
  import.meta.glob("../{pages/TodayPage,components/commercial,components/operator}/**/*.{ts,tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)
  .filter(([path]) => !path.includes(".test."))
  .map(([, src]) => src as string);

const mailtoSource = import.meta.glob("../components/commercial/MailtoEmailLink.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
})["../components/commercial/MailtoEmailLink.tsx"] as string;

const viteConfigSource = import.meta.glob("../../vite.config.ts", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../vite.config.ts"] as string;

const DASHBOARD_V1_API_PATHS = [
  "/health",
  "/operator/status",
  "/cases/warm",
  "/opportunities/equipment",
];

const LEGACY_API_PATH_FRAGMENTS = [
  "/dashboard",
  "/classification",
  "/commercial/purchase",
  '"/contacts"',
  "/organizations",
  "/outbound",
  "/meta/dashboard",
];

const LEGACY_PANEL_IMPORTS = [
  "ComprasTab",
  "ClassificationSection",
  "TabNav",
  "KpiCards",
  "OrganizationsSection",
  "ReadinessPanel",
  "HowToReadPanel",
  "PurchaseSignalsSection",
  "ConfirmedPurchaseEventsSection",
  "SyncWatermark",
];

const FORBIDDEN_UI_PATTERNS = [
  /\bbody_preview\b/,
  /\bemail_body\b/,
  /\bsource_path\b/,
  /\bsqlite_path\b/,
  /encodeURIComponent\([^)]*subject/i,
  /mailto:[^"']*\?subject=/i,
  /mailto:[^"']*&body=/i,
];

describe("Dashboard-2 safety (mounted Today)", () => {
  it("App.tsx mounts TodayPage only (no legacy commercial panels)", () => {
    expect(appSource).toContain("TodayPage");
    for (const symbol of LEGACY_PANEL_IMPORTS) {
      expect(appSource, `App.tsx must not import or mount ${symbol}`).not.toContain(symbol);
    }
    expect(appSource).not.toMatch(/api\/client/);
    expect(appSource).not.toMatch(/\/legacy\//);
  });

  it("active runtime does not import parked legacy folder", () => {
    const activeSources = [appSource, todayPageSource, operatorClientSource].join("\n");
    expect(activeSources).not.toMatch(/\/legacy\//);
    expect(activeSources).not.toMatch(/legacy\/api\/client/);
  });

  it("operatorClient calls only apps/api Dashboard routes", () => {
    const paths = [...operatorClientSource.matchAll(/operatorApiUrl\(\s*["']([^"']+)["']/g)].map(
      (m) => m[1],
    );
    expect(paths.sort()).toEqual(DASHBOARD_V1_API_PATHS.sort());
    for (const legacy of LEGACY_API_PATH_FRAGMENTS) {
      expect(operatorClientSource, `legacy route ${legacy}`).not.toContain(legacy);
    }
  });

  it("operatorClient uses GET /contacts/{email} with encoded path only", () => {
    expect(operatorClientSource).toContain("fetchContactProfile");
    expect(operatorClientSource).toMatch(/encodeURIComponent/);
    expect(operatorClientSource).toMatch(/\/contacts\/\$\{encodeURIComponent/);
    expect(operatorClientSource).not.toMatch(/operatorApiUrl\(\s*["']\/contacts["']/);
  });

  it("TodayPage does not call legacy api/client", () => {
    expect(todayPageSource).not.toMatch(/from\s+["'][^"']*api\/client["']/);
    expect(todayPageSource).not.toMatch(/api\/client/);
    expect(todayPageSource).toMatch(/fetchWarmCases|fetchEquipmentOpportunities/);
    expect(todayPageSource).toMatch(/ContactProfilePanel/);
    expect(commercialMountedSources.join("\n")).toMatch(/Read-only contact profile/);
  });

  it("operatorClient uses GET fetch only", () => {
    expect(operatorClientSource).toMatch(/method:\s*["']GET["']/);
    expect(operatorClientSource).not.toMatch(/method:\s*["'](POST|PUT|PATCH|DELETE)["']/i);
  });

  it("operatorClient requires env in production (no localhost fallback)", () => {
    expect(operatorClientSource).toMatch(/MODE\s*===\s*["']production["']/);
    expect(operatorClientSource).toContain("OperatorApiConfigError");
    expect(operatorClientSource).not.toMatch(/DEFAULT_API_BASE|127\.0\.0\.1:8001/);
  });

  it("mounted commercial UI avoids sensitive fields and mailto prefills", () => {
    const blob = commercialMountedSources.join("\n");
    for (const pattern of FORBIDDEN_UI_PATTERNS) {
      expect(blob, pattern.toString()).not.toMatch(pattern);
    }
    expect(operatorClientSource).toContain("parseWarmCasesResponse");
    expect(operatorClientSource).toContain("parseEquipmentOpportunitiesResponse");
  });

  it("warm cases table does not mount mailto composer links", () => {
    const warmTableSource = import.meta.glob("../components/commercial/WarmCasesTable.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    })["../components/commercial/WarmCasesTable.tsx"] as string;
    expect(warmTableSource).not.toContain("MailtoEmailLink");
    expect(warmTableSource).toContain("CopyTextButton");
    expect(warmTableSource).toContain("ContactEmailButton");
  });

  it("mailto helper is email-only", () => {
    expect(mailtoSource).toContain("buildMailtoHref");
    expect(mailtoSource).toMatch(/mailto:\$\{trimmed\}/);
    expect(mailtoSource).not.toMatch(/subject=|body=/i);
  });

  it("parked legacy tree exists but is outside vitest", () => {
    const legacyReadme = import.meta.glob("../legacy/README.md", {
      query: "?raw",
      import: "default",
      eager: true,
    })["../legacy/README.md"] as string;
    expect(legacyReadme).toContain("PARKED");
    expect(legacyReadme).toContain("Not mounted");
  });

  it("vite dev proxy exposes Dashboard v1 API routes only", () => {
    expect(viteConfigSource).toMatch(/["']\/health["']/);
    expect(viteConfigSource).toMatch(/["']\/operator["']/);
    expect(viteConfigSource).toMatch(/["']\/cases["']/);
    expect(viteConfigSource).toMatch(/["']\/opportunities["']/);
    expect(viteConfigSource).toMatch(/["']\/contacts["']/);
    expect(viteConfigSource).not.toMatch(/["']\/dashboard["']/);
    expect(viteConfigSource).not.toMatch(/["']\/classification["']/);
    expect(viteConfigSource).not.toMatch(/["']\/commercial["']/);
  });
});
