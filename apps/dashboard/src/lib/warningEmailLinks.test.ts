import { describe, expect, it } from "vitest";
import { extractEmailsFromWarning, parseWarningSegments } from "./warningEmailLinks";

describe("warningEmailLinks", () => {
  it("extracts emails from warning text", () => {
    const text =
      "Quiteca: jorgepc@quiteca.cl contacted April 2026; contacto@quiteca.cl requires review.";
    expect(extractEmailsFromWarning(text)).toEqual([
      "jorgepc@quiteca.cl",
      "contacto@quiteca.cl",
    ]);
  });

  it("parses inline segments for drilldown buttons", () => {
    const segments = parseWarningSegments("FastLab (contacto@fastlab.cl): review before outreach.");
    expect(segments.some((s) => s.type === "email" && s.value === "contacto@fastlab.cl")).toBe(
      true,
    );
    expect(segments.filter((s) => s.type === "text").length).toBeGreaterThan(0);
  });
});
