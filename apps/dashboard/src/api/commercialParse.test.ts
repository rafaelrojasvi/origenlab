import { describe, expect, it } from "vitest";
import {
  normalizeWarmCaseItem,
  parseEquipmentOpportunitiesResponse,
  parseWarmCasesResponse,
} from "./commercialParse";

describe("commercialParse", () => {
  it("parseWarmCasesResponse tolerates empty and sparse payloads", () => {
    const parsed = parseWarmCasesResponse({
      meta: { reduced_mode: true, note: "no enrichment" },
      items: [
        {
          contact_email: "a@b.cl",
          last_seen_at: null,
          subject: null,
          snippet: undefined,
          body_preview: "must not surface",
          sqlite_path: "/hidden/db.sqlite",
        },
        null,
      ],
    });

    expect(parsed.items).toHaveLength(2);
    expect(parsed.items[0].contact_email).toBe("a@b.cl");
    expect(parsed.items[0].last_seen_at).toBeNull();
    expect(parsed.items[0].snippet).toBe("");
    expect(parsed.items[0].gmail_url).toBeNull();
    expect(parsed.meta.reduced_mode).toBe(true);
    expect(parsed.meta.note).toContain("no enrichment");
    expect(parsed.items[1].case_id).toBe("warm-row-2");
    expect(JSON.stringify(parsed)).not.toContain("body_preview");
    expect(JSON.stringify(parsed)).not.toContain("sqlite_path");
  });

  it("parseEquipmentOpportunitiesResponse strips source_path and null fields", () => {
    const parsed = parseEquipmentOpportunitiesResponse({
      meta: {
        data_source: "postgres_mirror",
        source_path: "/var/data/queue/secret.csv",
        count: 0,
        reduced_mode: true,
        note: "mirror lag",
      },
      items: [],
    });

    expect(parsed.items).toEqual([]);
    expect(parsed.meta.reduced_mode).toBe(true);
    expect("source_path" in parsed.meta).toBe(false);
    expect(JSON.stringify(parsed.meta)).not.toContain("secret.csv");
  });

  it("normalizeWarmCaseItem redacts path-like preview text", () => {
    const row = normalizeWarmCaseItem(
      { snippet: "see /home/user/data/emails.sqlite for details" },
      0,
    );
    expect(row.snippet).toContain("[path redacted]");
    expect(row.snippet).not.toContain("/home/user");
  });
});
