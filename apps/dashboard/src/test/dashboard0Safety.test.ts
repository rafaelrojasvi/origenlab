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

const warmTableSource = import.meta.glob("../components/commercial/WarmCasesTable.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
})["../components/commercial/WarmCasesTable.tsx"] as string;

const equipmentTableSource = import.meta.glob(
  "../components/commercial/EquipmentOpportunitiesTable.tsx",
  {
    query: "?raw",
    import: "default",
    eager: true,
  },
)["../components/commercial/EquipmentOpportunitiesTable.tsx"] as string;

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

describe("Dashboard-0/1 safety (mounted Today)", () => {
  it("App.tsx mounts TodayPage only (no legacy commercial panels)", () => {
    expect(appSource).toContain("TodayPage");
    for (const symbol of LEGACY_PANEL_IMPORTS) {
      expect(appSource, `App.tsx must not import or mount ${symbol}`).not.toContain(symbol);
    }
  });

  it("operatorClient calls only apps/api Dashboard routes", () => {
    const paths = [...operatorClientSource.matchAll(/operatorApiUrl\(\s*["']([^"']+)["']/g)].map(
      (m) => m[1],
    );
    expect(paths.sort()).toEqual(DASHBOARD_V1_API_PATHS.sort());
  });

  it("operatorClient uses GET fetch only", () => {
    expect(operatorClientSource).toMatch(/method:\s*["']GET["']/);
    expect(operatorClientSource).not.toMatch(/method:\s*["'](POST|PUT|PATCH|DELETE)["']/i);
  });

  it("operatorClient requires env in production (no localhost fallback)", () => {
    expect(operatorClientSource).toMatch(/MODE\s*===\s*["']production["']/);
    expect(operatorClientSource).toContain("OperatorApiConfigError");
    expect(operatorClientSource).toContain("PRODUCTION_API_BASE_URL_REQUIRED");
    expect(operatorClientSource).not.toMatch(/DEFAULT_API_BASE|127\.0\.0\.1:8001/);
  });

  it("TodayPage uses operatorClient only (not legacy api/client)", () => {
    expect(todayPageSource).not.toMatch(/from\s+["'][^"']*api\/client["']/);
    expect(todayPageSource).not.toMatch(/api\/client/);
    expect(todayPageSource).toMatch(/fetchWarmCases|fetchEquipmentOpportunities/);
    expect(todayPageSource).not.toMatch(/sqlite_path/);
    expect(todayPageSource).not.toMatch(/body_preview|email_body|["']body["']/);
  });

  it("commercial tables do not render bodies or filesystem paths", () => {
    for (const src of [warmTableSource, equipmentTableSource, todayPageSource]) {
      expect(src).not.toMatch(/body_preview|email_body|\.body\b/);
      expect(src).not.toMatch(/source_path/);
    }
  });

  it("vite dev proxy exposes Dashboard v1 API routes only", () => {
    expect(viteConfigSource).toMatch(/["']\/health["']/);
    expect(viteConfigSource).toMatch(/["']\/operator["']/);
    expect(viteConfigSource).toMatch(/["']\/cases["']/);
    expect(viteConfigSource).toMatch(/["']\/opportunities["']/);
    expect(viteConfigSource).not.toMatch(/["']\/dashboard["']/);
    expect(viteConfigSource).not.toMatch(/["']\/classification["']/);
    expect(viteConfigSource).not.toMatch(/["']\/commercial["']/);
  });
});
