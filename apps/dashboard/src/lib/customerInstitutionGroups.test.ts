import { describe, expect, it } from "vitest";
import type { LeadProspectListItemUi } from "../api/leadIntelTypes";
import {
  buildCustomerInstitutionGroups,
  filterCustomerInstitutionGroups,
  institutionNextAction,
  institutionStatusChips,
  normalizeInstitutionKey,
} from "./customerInstitutionGroups";

function row(partial: Partial<LeadProspectListItemUi> & Pick<LeadProspectListItemUi, "prospect_key" | "organization_name">): LeadProspectListItemUi {
  return {
    contact_name: null,
    email: null,
    domain: null,
    sector: null,
    region: null,
    buyer_type: null,
    product_angle: null,
    final_score: 50,
    classification: "net_new_safe_review",
    status: "review",
    spanish_message_angle: null,
    recommended_next_action: null,
    risk_flags: "",
    evidence_url: null,
    is_blocked: false,
    campaign_bucket: null,
    source_type: "deepsearch",
    dataset_label: null,
    gmail_first_contacted_at: null,
    gmail_last_contacted_at: null,
    gmail_sent_count: null,
    gmail_received_count: null,
    gmail_latest_subject_safe: null,
    ...partial,
  };
}

describe("customerInstitutionGroups", () => {
  it("groups same domain together", () => {
    const groups = buildCustomerInstitutionGroups([
      row({
        prospect_key: "a1",
        organization_name: "Acme Labs",
        domain: "acme.cl",
        email: "a@acme.cl",
      }),
      row({
        prospect_key: "a2",
        organization_name: "ACME Laboratorios",
        domain: "acme.cl",
        email: "b@acme.cl",
      }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.contactsWithEmail).toBe(2);
    expect(groups[0]?.domain).toBe("acme.cl");
  });

  it("falls back to organization name when domain missing", () => {
    expect(
      normalizeInstitutionKey(
        row({ prospect_key: "x", organization_name: "Hospital Sur", domain: null }),
      ),
    ).toBe("org:hospital sur");
    const groups = buildCustomerInstitutionGroups([
      row({ prospect_key: "h1", organization_name: "Hospital Sur", email: "x@hospital.cl" }),
      row({ prospect_key: "h2", organization_name: "Hospital Sur", email: null }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.contactsWithEmail).toBe(1);
    expect(groups[0]?.contactsMissingEmail).toBe(1);
  });

  it("counts contacts with and without email", () => {
    const groups = buildCustomerInstitutionGroups([
      row({
        prospect_key: "m1",
        organization_name: "Mix Co",
        domain: "mix.cl",
        email: "one@mix.cl",
      }),
      row({
        prospect_key: "m2",
        organization_name: "Mix Co",
        domain: "mix.cl",
        email: null,
        classification: "research_only_contact_needed",
      }),
    ]);
    expect(groups[0]?.contactsWithEmail).toBe(1);
    expect(groups[0]?.contactsMissingEmail).toBe(1);
  });

  it("detects Gmail history", () => {
    const groups = buildCustomerInstitutionGroups([
      row({
        prospect_key: "g1",
        organization_name: "Gmail Co",
        domain: "gmail.cl",
        email: "ana@gmail.cl",
        source_type: "gmail_historico",
        gmail_sent_count: 2,
        gmail_received_count: 1,
        gmail_last_contacted_at: "2025-01-01",
      }),
    ]);
    expect(groups[0]?.hasGmailHistory).toBe(true);
    expect(groups[0]?.totalGmailSent).toBe(2);
  });

  it("detects blocked and risk", () => {
    const groups = buildCustomerInstitutionGroups([
      row({
        prospect_key: "b1",
        organization_name: "Blocked Co",
        domain: "blocked.cl",
        is_blocked: true,
        risk_flags: "dominio_en_historial_origenlab",
      }),
    ]);
    expect(groups[0]?.anyBlocked).toBe(true);
    expect(groups[0]?.anyRisk).toBe(true);
    expect(institutionNextAction(groups[0]!)).toMatch(/bloqueo/i);
    expect(institutionStatusChips(groups[0]!).some((chip) => chip.code === "blocked")).toBe(true);
  });

  it("chooses safe next action labels", () => {
    const missingEmail = buildCustomerInstitutionGroups([
      row({
        prospect_key: "r1",
        organization_name: "Research Co",
        domain: "research.cl",
        email: null,
        classification: "research_only_contact_needed",
      }),
    ])[0]!;
    expect(institutionNextAction(missingEmail)).toMatch(/Investigar email/i);

    const gmail = buildCustomerInstitutionGroups([
      row({
        prospect_key: "g2",
        organization_name: "Hist Co",
        domain: "hist.cl",
        email: "x@hist.cl",
        gmail_last_contacted_at: "2024-06-01",
        gmail_sent_count: 1,
      }),
    ])[0]!;
    expect(institutionNextAction(gmail)).toMatch(/seguimiento/i);
  });

  it("filters by preset and score", () => {
    const groups = buildCustomerInstitutionGroups([
      row({
        prospect_key: "s1",
        organization_name: "Safe Co",
        domain: "safe.cl",
        email: "ok@safe.cl",
        final_score: 90,
      }),
      row({
        prospect_key: "s2",
        organization_name: "Risk Co",
        domain: "risk.cl",
        email: "bad@risk.cl",
        is_blocked: true,
      }),
    ]);
    const gmailOnly = filterCustomerInstitutionGroups(groups, {
      search: "",
      preset: "blocked_risk",
      sector: "",
      region: "",
      minScore: null,
    });
    expect(gmailOnly).toHaveLength(1);
    expect(gmailOnly[0]?.institutionName).toBe("Risk Co");

    const highScore = filterCustomerInstitutionGroups(groups, {
      search: "",
      preset: "all",
      sector: "",
      region: "",
      minScore: 85,
    });
    expect(highScore).toHaveLength(1);
    expect(highScore[0]?.institutionName).toBe("Safe Co");
  });
});
