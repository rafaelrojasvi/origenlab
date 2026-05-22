import { describe, expect, it } from "vitest";
import { assertNoForbiddenContactKeys, parseContactDetailResponse } from "./contactParse";

const SAMPLE = {
  meta: {
    data_source: "sqlite",
    read_only: true,
    reduced_mode: false,
    note: "",
  },
  contact: {
    email: "known@cliente.cl",
    normalized_email: "known@cliente.cl",
    name: "Known Client",
    domain: "cliente.cl",
    organization_name: "Cliente SA",
    organization_domain: "cliente.cl",
    last_seen_at: "2026-05-19",
    first_seen_at: "2026-01-01",
    message_count: 12,
  },
  outreach: {
    state: "contacted",
    last_contacted_at: "2026-05-18",
    source: "test",
    notes: "operator note",
    do_not_repeat: true,
    suppressed_email: false,
    suppressed_domain: false,
  },
  sent_history: {
    sent_count: 1,
    latest_sent_at: "2026-05-10",
    latest_subject: "Cotización equipo",
  },
  warnings: ["/secret/path/emails.sqlite missing"],
};

describe("contactParse", () => {
  it("parses safe contact profile fields", () => {
    const parsed = parseContactDetailResponse(SAMPLE);
    expect(parsed.contact.normalized_email).toBe("known@cliente.cl");
    expect(parsed.outreach.do_not_repeat).toBe(true);
    expect(parsed.sent_history.latest_subject).toBe("Cotización equipo");
    expect(parsed.warnings[0]).toContain("[path redacted]");
  });

  it("rejects forbidden top-level keys", () => {
    expect(() =>
      assertNoForbiddenContactKeys({ ...SAMPLE, body_preview: "secret" }),
    ).toThrow(/forbidden field/);
    expect(() =>
      assertNoForbiddenContactKeys({ ...SAMPLE, sqlite_path: "/tmp/x.sqlite" }),
    ).toThrow(/forbidden field/);
  });
});
