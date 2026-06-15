import { describe, expect, it } from "vitest";
import { formatDashboardDateShort, formatDashboardDateTime, formatEquipmentCloseDate } from "./dashboardDateFormat";

describe("dashboardDateFormat", () => {
  it("returns em dash for null and empty", () => {
    expect(formatDashboardDateTime(null)).toBe("—");
    expect(formatDashboardDateTime("")).toBe("—");
    expect(formatDashboardDateShort(undefined)).toBe("—");
  });

  it("formats ISO timestamps in es-CL without raw ISO in output", () => {
    const formatted = formatDashboardDateTime("2026-06-10T13:38:54+00:00");
    expect(formatted).not.toMatch(/T13:38:54\+00:00/);
    expect(formatted).toMatch(/2026/);
    expect(formatted).toMatch(/\d{1,2}:\d{2}/);
  });

  it("formats short date without time", () => {
    const formatted = formatDashboardDateShort("2026-06-10T13:38:54+00:00");
    expect(formatted).not.toMatch(/13:38/);
    expect(formatted).toMatch(/2026/);
  });

  it("formats Chilean and ISO close dates for equipment", () => {
    const chilean = formatEquipmentCloseDate("17/06/2026 19:00:00");
    expect(chilean).not.toBe("17/06/2026 19:00:00");
    expect(chilean).toMatch(/2026/);
    expect(chilean).toMatch(/19:00/);

    expect(
      formatEquipmentCloseDate("2026-06-17T19:00:00", "2026-06-17T19:00:00-04:00"),
    ).toBe("17 jun 2026, 19:00");
  });
});
