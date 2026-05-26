import { describe, expect, it } from "vitest";
import {
  DASHBOARD_PRODUCTION_HOST,
  isDashboardHostAllowed,
  normalizeDashboardHostname,
} from "./dashboardHostGuard";

describe("dashboardHostGuard", () => {
  it("normalizes hostname casing and whitespace", () => {
    expect(normalizeDashboardHostname("  Dashboard.OrigenLab.CL  ")).toBe(
      "dashboard.origenlab.cl",
    );
  });

  it("allows production host in production builds", () => {
    expect(
      isDashboardHostAllowed(DASHBOARD_PRODUCTION_HOST, { productionBuild: true }),
    ).toBe(true);
  });

  it("allows localhost and 127.0.0.1 in production builds", () => {
    expect(isDashboardHostAllowed("localhost", { productionBuild: true })).toBe(true);
    expect(isDashboardHostAllowed("127.0.0.1", { productionBuild: true })).toBe(true);
  });

  it("blocks raw Render hostname in production builds", () => {
    expect(
      isDashboardHostAllowed("origenlab-dashboard.onrender.com", {
        productionBuild: true,
      }),
    ).toBe(false);
  });

  it("allows non-listed hosts only in non-production builds", () => {
    expect(
      isDashboardHostAllowed("origenlab-dashboard.onrender.com", {
        productionBuild: false,
      }),
    ).toBe(true);
  });
});
