import { describe, expect, it } from "vitest";

const handoff = import.meta.glob("../../docs/V1_FREEZE_OPERATOR_HANDOFF.md", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../docs/V1_FREEZE_OPERATOR_HANDOFF.md"] as string;

const matrix = import.meta.glob("../../docs/BACKEND_MATRIX_VALIDATION.md", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../docs/BACKEND_MATRIX_VALIDATION.md"] as string;

describe("Dashboard-2 freeze handoff docs", () => {
  it("documents read-only contact drilldown and forbidden UI", () => {
    expect(handoff).toMatch(/GET \/contacts\/\{email\}/);
    expect(handoff).toMatch(/side panel/i);
    expect(handoff).toMatch(/mark-contacted|status-edit/i);
    expect(handoff).toMatch(/raw email bodies|body_preview|source_path|sqlite_path/i);
    expect(handoff).toMatch(/Postgres mirror is not send\/outreach truth/);
  });

  it("records SQLite and disposable Postgres validation", () => {
    expect(handoff).toMatch(/Dashboard-2 freeze validation/i);
    expect(handoff).toMatch(/SQLite.*Passed|Passed.*SQLite/i);
    expect(handoff).toMatch(/5433/);
    expect(handoff).toMatch(/Gmail was not mutated|Gmail.*not mutated/i);
    expect(handoff).toMatch(/production\/scratch Postgres.*not/i);
  });

  it("documents contact smoke commands and return to SQLite warning", () => {
    expect(handoff).toMatch(/npm run smoke:contacts/);
    expect(handoff).toMatch(/EXPECT_BACKEND=postgres npm run smoke:contacts/);
    expect(handoff).toMatch(/smoke:proxy/);
    expect(handoff).toMatch(/Return to SQLite after Postgres validation/);
    expect(handoff).toMatch(/unset ORIGENLAB_API_BACKEND/);
    expect(handoff).toMatch(/unset ORIGENLAB_POSTGRES_URL/);
  });

  it("matrix doc aligns with contact smoke and validation", () => {
    expect(matrix).toMatch(/smoke:contacts/);
    expect(matrix).toMatch(/Dashboard-2 freeze validation/i);
    expect(matrix).toMatch(/127\.0\.0\.1:5433/);
    expect(matrix).toMatch(/legacy email-pipeline API.*removed|Removed.*Phase 6/i);
  });

  it("documents Dashboard-2.5 read-only usability", () => {
    expect(handoff).toMatch(/Dashboard-2\.5/);
    expect(handoff).toMatch(/Hide internal OrigenLab contacts/i);
    expect(handoff).toMatch(/origenlab\.cl.*labdelivery\.cl|labdelivery\.cl.*origenlab\.cl/i);
    expect(handoff).toMatch(/Warning email drilldown|warnings.*email/i);
    expect(handoff).toMatch(/Humanized labels|human labels/i);
    expect(handoff).toMatch(/OutreachTruthGuide/i);
    expect(handoff).toMatch(/client-side only|in-browser only/i);
    expect(handoff).toMatch(/No.*mailto.*warnings|No.*mailto, send/i);
    expect(handoff).toMatch(/mark-contacted|status-edit/i);
    expect(handoff).toMatch(/Phase 6|legacy.*removed|removed.*legacy/i);
  });
});
