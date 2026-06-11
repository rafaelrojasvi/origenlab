import { describe, expect, it } from "vitest";
import { formatDashboardDateShort, formatDashboardDateTime } from "./dashboardDateFormat";

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

  it("returns original string when parsing fails", () => {
    expect(formatDashboardDateTime("not-a-date")).toBe("not-a-date");
  });
});
