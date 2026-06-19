import { describe, expect, it, vi } from "vitest";
import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import {
  EQUIPMENT_WATCHLIST_MAX_KEYS,
  EQUIPMENT_WATCHLIST_STORAGE_KEY,
  getEquipmentWatchlistKey,
  readEquipmentWatchlist,
  toggleEquipmentWatchlistKey,
  writeEquipmentWatchlist,
} from "./equipmentWatchlist";

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

function createMemoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear() {
      data.clear();
    },
    getItem(key: string) {
      return data.get(key) ?? null;
    },
    key(index: number) {
      return [...data.keys()][index] ?? null;
    },
    removeItem(key: string) {
      data.delete(key);
    },
    setItem(key: string, value: string) {
      data.set(key, value);
    },
  };
}

describe("equipmentWatchlist", () => {
  it("uses opportunity_key when present", () => {
    expect(
      getEquipmentWatchlistKey(
        baseItem({
          opportunity_key: "opp-123",
          codigo_licitacion: "LP-999",
        }),
      ),
    ).toBe("opp-123");
  });

  it("falls back safely when opportunity_key is missing", () => {
    expect(getEquipmentWatchlistKey(baseItem())).toBe("eq-1-LP-001");
    expect(
      getEquipmentWatchlistKey(
        baseItem({
          codigo_licitacion: "",
          buyer: "Clinica",
          priority_rank: 2,
        }),
      ),
    ).toBe("eq-2-Clinica");
  });

  it("returns empty Set for empty or malformed storage", () => {
    const storage = createMemoryStorage();
    expect(readEquipmentWatchlist(storage)).toEqual(new Set());
    storage.setItem(EQUIPMENT_WATCHLIST_STORAGE_KEY, "{not-json");
    expect(readEquipmentWatchlist(storage)).toEqual(new Set());
    storage.setItem(EQUIPMENT_WATCHLIST_STORAGE_KEY, JSON.stringify({ keys: ["a"] }));
    expect(readEquipmentWatchlist(storage)).toEqual(new Set());
    storage.setItem(EQUIPMENT_WATCHLIST_STORAGE_KEY, JSON.stringify([1, "ok", "", "  "]));
    expect(readEquipmentWatchlist(storage)).toEqual(new Set(["ok"]));
  });

  it("round trips keys through write and read", () => {
    const storage = createMemoryStorage();
    writeEquipmentWatchlist(new Set(["a", "b"]), storage);
    expect(readEquipmentWatchlist(storage)).toEqual(new Set(["a", "b"]));
  });

  it("toggle adds and removes keys", () => {
    let keys = new Set<string>();
    keys = toggleEquipmentWatchlistKey(keys, "eq-1");
    expect(keys).toEqual(new Set(["eq-1"]));
    keys = toggleEquipmentWatchlistKey(keys, "eq-1");
    expect(keys).toEqual(new Set());
  });

  it("caps stored keys at 500", () => {
    const storage = createMemoryStorage();
    const keys = new Set(Array.from({ length: 501 }, (_, index) => `key-${index}`));
    writeEquipmentWatchlist(keys, storage);
    expect(readEquipmentWatchlist(storage).size).toBe(EQUIPMENT_WATCHLIST_MAX_KEYS);

    const toggled = toggleEquipmentWatchlistKey(new Set(Array.from({ length: 500 }, (_, i) => `k-${i}`)), "k-new");
    expect(toggled.size).toBe(EQUIPMENT_WATCHLIST_MAX_KEYS);
    expect(toggled.has("k-new")).toBe(true);
    expect(toggled.has("k-0")).toBe(false);
  });

  it("does not crash when storage throws", () => {
    const storage = {
      getItem: vi.fn(() => {
        throw new Error("blocked");
      }),
      setItem: vi.fn(() => {
        throw new Error("blocked");
      }),
    } as unknown as Storage;

    expect(readEquipmentWatchlist(storage)).toEqual(new Set());
    expect(() => writeEquipmentWatchlist(new Set(["a"]), storage)).not.toThrow();
  });
});
