import { describe, expect, it } from "vitest";
import { leadProspectsQueryFromOrigin } from "./prospectOriginQuery";

describe("leadProspectsQueryFromOrigin", () => {
  it("maps deepsearch to source_type", () => {
    expect(
      leadProspectsQueryFromOrigin("deepsearch", { limit: 50 }),
    ).toEqual({ limit: 50, source_type: "deepsearch" });
  });

  it("maps blocked to blocked_only", () => {
    expect(
      leadProspectsQueryFromOrigin("blocked", { limit: 50 }),
    ).toEqual({ limit: 50, blocked_only: true, include_blocked: true });
  });

  it("maps same domain to classification", () => {
    expect(
      leadProspectsQueryFromOrigin("same_domain_contacted_review", { limit: 50 }),
    ).toEqual({ limit: 50, classification: "same_domain_contacted_review" });
  });
});
