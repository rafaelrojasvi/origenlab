import { describe, expect, it } from "vitest";
import { pickContactEmailFromLists } from "../lib/smokeContactPick";

describe("smoke contact drilldown helpers", () => {
  it("picks email from warm cases first", () => {
    const picked = pickContactEmailFromLists(
      { items: [{ contact_email: "warm@cliente.cl" }] },
      { items: [{ contact_email: "eq@hospital.cl" }] },
    );
    expect(picked).toEqual({ email: "warm@cliente.cl", source: "warm_cases" });
  });

  it("falls back to equipment contact_email", () => {
    const picked = pickContactEmailFromLists(
      { items: [{ contact_email: "" }] },
      { items: [{ contact_email: "eq@hospital.cl" }] },
    );
    expect(picked).toEqual({ email: "eq@hospital.cl", source: "equipment" });
  });

  it("returns null when no valid email (smoke skip, not failure)", () => {
    expect(
      pickContactEmailFromLists(
        { items: [{ contact_email: "no-at-sign" }] },
        { items: [] },
      ),
    ).toBeNull();
  });
});
