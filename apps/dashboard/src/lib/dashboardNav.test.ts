import { describe, expect, it } from "vitest";
import {
  DASHBOARD_NAV_GROUPS,
  DASHBOARD_NAV_ITEMS,
  dashboardSectionGroupLabel,
  dashboardSectionLabel,
} from "./dashboardNav";

describe("dashboardNav", () => {
  it("groups contain all sections without duplicates", () => {
    const ids = DASHBOARD_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id));
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.length).toBe(DASHBOARD_NAV_ITEMS.length);
  });

  it("maps section labels and groups", () => {
    expect(dashboardSectionLabel("today")).toBe("Hoy");
    expect(dashboardSectionGroupLabel("deals")).toBe("Comercial");
    expect(dashboardSectionGroupLabel("system")).toBe("Sistema");
  });
});
