import { describe, expect, it, vi } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  WARM_CASE_REVIEW_LABELS_MAX_ENTRIES,
  WARM_CASE_REVIEW_LABELS_STORAGE_KEY,
  countReviewedWarmCases,
  getWarmCaseReviewKey,
  readWarmCaseReviewLabels,
  setWarmCaseReviewLabel,
  writeWarmCaseReviewLabels,
  type WarmCaseReviewLabel,
} from "./warmCaseReviewLabels";

function baseRow(overrides: Partial<WarmCaseItem> = {}): WarmCaseItem {
  return {
    case_id: "gmail-contacto-1",
    last_email_id: 1,
    last_seen_at: "2026-05-19T10:00:00-04:00",
    account_name: "ACME Lab",
    contact_email: "buyer@acme.cl",
    subject: "Re: centrifuge quote",
    category: "client_reply",
    status: "open",
    next_action: "follow_up",
    equipment_signal: "centrifuge",
    snippet: "Short preview only",
    gmail_url: null,
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

describe("warmCaseReviewLabels", () => {
  it("uses case_id when present", () => {
    expect(getWarmCaseReviewKey(baseRow())).toBe("gmail-contacto-1");
  });

  it("falls back deterministically when case_id is missing", () => {
    expect(
      getWarmCaseReviewKey(
        baseRow({
          case_id: "",
          contact_email: "buyer@acme.cl",
          subject: "Quote",
          grouped_email_count: 3,
          last_seen_at: "2026-05-19T10:00:00Z",
        }),
      ),
    ).toBe("warm-fb-buyer@acme.cl|Quote|3|2026-05-19T10:00:00Z");
  });

  it("returns empty map for empty or malformed storage", () => {
    const storage = createMemoryStorage();
    expect(readWarmCaseReviewLabels(storage)).toEqual({});
    storage.setItem(WARM_CASE_REVIEW_LABELS_STORAGE_KEY, "{not-json");
    expect(readWarmCaseReviewLabels(storage)).toEqual({});
    storage.setItem(WARM_CASE_REVIEW_LABELS_STORAGE_KEY, JSON.stringify(["util"]));
    expect(readWarmCaseReviewLabels(storage)).toEqual({});
    storage.setItem(
      WARM_CASE_REVIEW_LABELS_STORAGE_KEY,
      JSON.stringify({ "case-1": "util", "case-2": "invalid", "": "util" }),
    );
    expect(readWarmCaseReviewLabels(storage)).toEqual({ "case-1": "util" });
  });

  it("round trips labels through write and read", () => {
    const storage = createMemoryStorage();
    writeWarmCaseReviewLabels({ "case-1": "util", "case-2": "no_util" }, storage);
    expect(readWarmCaseReviewLabels(storage)).toEqual({
      "case-1": "util",
      "case-2": "no_util",
    });
  });

  it("removes label when set to blank", () => {
    let labels: Record<string, WarmCaseReviewLabel> = {
      "case-1": "util",
      "case-2": "no_util",
    };
    labels = setWarmCaseReviewLabel(labels, "case-1", "");
    expect(labels).toEqual({ "case-2": "no_util" });
    writeWarmCaseReviewLabels(labels, createMemoryStorage());
  });

  it("caps stored entries at 500", () => {
    const storage = createMemoryStorage();
    const labels = Object.fromEntries(
      Array.from({ length: 501 }, (_, index) => [`key-${index}`, "util" as const]),
    );
    writeWarmCaseReviewLabels(labels, storage);
    expect(Object.keys(readWarmCaseReviewLabels(storage))).toHaveLength(
      WARM_CASE_REVIEW_LABELS_MAX_ENTRIES,
    );

    const capped = setWarmCaseReviewLabel(
      Object.fromEntries(
        Array.from({ length: 500 }, (_, index) => [`key-${index}`, "util" as const]),
      ),
      "key-new",
      "util",
    );
    expect(Object.keys(capped)).toHaveLength(WARM_CASE_REVIEW_LABELS_MAX_ENTRIES);
    expect(capped["key-new"]).toBe("util");
    expect(capped["key-0"]).toBeUndefined();
  });

  it("counts reviewed labels", () => {
    expect(countReviewedWarmCases({})).toBe(0);
    expect(countReviewedWarmCases({ a: "util", b: "", c: "no_util" })).toBe(2);
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

    expect(readWarmCaseReviewLabels(storage)).toEqual({});
    expect(() => writeWarmCaseReviewLabels({ a: "util" }, storage)).not.toThrow();
  });
});
