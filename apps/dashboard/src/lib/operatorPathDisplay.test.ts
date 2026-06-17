import { describe, expect, it } from "vitest";
import {
  formatOperatorPathDisplay,
  formatRedactedPathLabel,
  formatSectionPathDisplay,
} from "./operatorPathDisplay";

describe("operatorPathDisplay", () => {
  it("formatRedactedPathLabel includes basename, kind, and redacted flag", () => {
    expect(
      formatRedactedPathLabel({
        redacted: true,
        basename: "current",
        kind: "directory",
      }),
    ).toBe("current (directory, redacted)");
  });

  it("formatOperatorPathDisplay prefers redacted info over raw path", () => {
    expect(
      formatOperatorPathDisplay("/home/ops/reports/out/active/current", {
        redacted: true,
        basename: "current",
        kind: "directory",
      }),
    ).toBe("current (directory, redacted)");
  });

  it("formatOperatorPathDisplay falls back to legacy raw path", () => {
    expect(formatOperatorPathDisplay("/legacy/path/to/current", null)).toBe(
      "/legacy/path/to/current",
    );
  });

  it("formatSectionPathDisplay reads nested path_info entries", () => {
    expect(
      formatSectionPathDisplay(
        "published_queue",
        "/home/ops/reports/out/active/current/equipment_first_operator_queue_20260616.csv",
        {
          published_queue: {
            redacted: true,
            basename: "equipment_first_operator_queue_20260616.csv",
            kind: "file",
          },
        },
      ),
    ).toBe("equipment_first_operator_queue_20260616.csv (file, redacted)");
  });
});
