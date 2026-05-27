import { describe, expect, it } from "vitest";
import { isEquipmentFeedUnavailable } from "./equipmentFeedStatus";

describe("isEquipmentFeedUnavailable", () => {
  it("is true when meta.reduced_mode", () => {
    expect(isEquipmentFeedUnavailable({ reduced_mode: true })).toBe(true);
    expect(isEquipmentFeedUnavailable({ reduced_mode: false })).toBe(false);
    expect(isEquipmentFeedUnavailable(null)).toBe(false);
  });
});
