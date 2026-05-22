import { describe, expect, it } from "vitest";
import { isInternalOperatorContact } from "./internalContactFilter";

describe("internalContactFilter", () => {
  it("flags origenlab.cl and labdelivery.cl", () => {
    expect(isInternalOperatorContact("contacto@origenlab.cl")).toBe(true);
    expect(isInternalOperatorContact("Tatiana@OrigenLab.CL")).toBe(true);
    expect(isInternalOperatorContact("contacto@labdelivery.cl")).toBe(true);
  });

  it("does not flag external contacts", () => {
    expect(isInternalOperatorContact("kelly@ollital.com")).toBe(false);
    expect(isInternalOperatorContact("buyer@hospital.cl")).toBe(false);
  });
});
