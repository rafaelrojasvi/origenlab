import { describe, expect, it } from "vitest";
import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import { getEquipmentTriageBadges } from "./equipmentTriage";

const NOW = new Date("2026-06-15T12:00:00Z");

function baseItem(overrides: Partial<EquipmentOpportunityItem> = {}): EquipmentOpportunityItem {
  return {
    priority_rank: 1,
    codigo_licitacion: "LP-001",
    buyer: "Hospital",
    region: "RM",
    close_date: "01/07/2026",
    equipment_category: "centrifuge",
    item_description: "Centrifuge",
    next_action: "monitor",
    safe_channel: "mercado_publico_bid",
    supplier_needed: "no",
    contact_status: "review_required",
    contact_email: "buyer@hospital.cl",
    operator_note: "",
    ...overrides,
  };
}

describe("getEquipmentTriageBadges", () => {
  it("adds urgent Cotizar ahora for quote_now", () => {
    const badges = getEquipmentTriageBadges(baseItem({ next_action: "quote_now" }), { now: NOW });
    expect(badges[0]).toEqual({
      label: "Cotizar ahora",
      tone: "urgent",
      reason: expect.stringContaining("cotizar"),
    });
  });

  it("adds Cierre pronto when close_at is within 3 days", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({ close_at: "2026-06-17T19:00:00-04:00", close_date: "" }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Cierre pronto")).toBe(true);
  });

  it("adds Cierre pronto when Chilean close_date is within 3 days", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({ close_date: "17/06/2026", close_at: undefined }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Cierre pronto")).toBe(true);
  });

  it("adds Sin contacto when email is missing and status is unverified", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({
        contact_email: "",
        contact_status: "no_verified_buyer_email",
      }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Sin contacto")).toBe(true);
  });

  it("does not add Sin contacto when contact email is present", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({
        contact_email: "buyer@hospital.cl",
        contact_status: "no_verified_buyer_email",
      }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Sin contacto")).toBe(false);
  });

  it("adds Requiere proveedor for yes-like supplier_needed", () => {
    const badges = getEquipmentTriageBadges(baseItem({ supplier_needed: "yes" }), { now: NOW });
    expect(badges.some((badge) => badge.label === "Requiere proveedor")).toBe(true);
  });

  it("adds Solo Mercado Público for mercado_publico_only channel", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({ safe_channel: "mercado_publico_only" }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Solo Mercado Público")).toBe(true);
  });

  it("limits badges to three per row", () => {
    const badges = getEquipmentTriageBadges(
      baseItem({
        next_action: "quote_now",
        close_at: "2026-06-16T12:00:00Z",
        contact_email: "",
        contact_status: "no_verified_buyer_email",
        supplier_needed: "yes",
        safe_channel: "mercado_publico_only",
      }),
      { now: NOW },
    );
    expect(badges).toHaveLength(3);
    expect(badges.map((badge) => badge.label)).toEqual([
      "Cotizar ahora",
      "Cierre pronto",
      "Sin contacto",
    ]);
  });

  it("tolerates malformed close dates without throwing", () => {
    expect(() =>
      getEquipmentTriageBadges(
        baseItem({ close_date: "not-a-date", close_at: "also-bad" }),
        { now: NOW },
      ),
    ).not.toThrow();
    const badges = getEquipmentTriageBadges(
      baseItem({ close_date: "not-a-date", close_at: "also-bad" }),
      { now: NOW },
    );
    expect(badges.some((badge) => badge.label === "Cierre pronto")).toBe(false);
  });
});
