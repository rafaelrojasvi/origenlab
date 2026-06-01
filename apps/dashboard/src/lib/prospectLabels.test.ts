import { describe, expect, it } from "vitest";
import {
  evidenceSourceLabel,
  parseRiskFlagChips,
  prospectBuyerTypeLabel,
  prospectClassificationLabel,
} from "./prospectLabels";
import { buildPorQueImporta, buildMessagePreview } from "./prospectMessaging";
import type { LeadProspectDetailUi } from "../api/leadIntelTypes";
import { defaultLeadOriginFields } from "../test/fixtures/leadIntelFixtures";

describe("prospectLabels", () => {
  it("translates buyer_type tokens", () => {
    expect(prospectBuyerTypeLabel("laboratorio_acuicola")).toBe("Laboratorio acuícola");
    expect(prospectBuyerTypeLabel("centro_investigacion")).toBe("Centro de investigación");
    expect(prospectBuyerTypeLabel(null)).toBe("Sin clasificar");
  });

  it("translates classification labels", () => {
    expect(prospectClassificationLabel("same_domain_contacted_review")).toBe(
      "Revisar historial previo",
    );
  });

  it("translates risk flags to chips", () => {
    const chips = parseRiskFlagChips("lead_status=net_new_candidate,dominio_en_historial_origenlab");
    expect(chips.map((c) => c.label)).toContain("Nuevo según investigación");
    expect(chips.map((c) => c.label)).toContain("Dominio con historial OrigenLab");
    expect(chips.some((c) => c.label.includes("lead_status="))).toBe(false);
  });

  it("maps evidence source to friendly label", () => {
    expect(
      evidenceSourceLabel("sernapesca_entidades_analisis", "https://www.sernapesca.cl/foo"),
    ).toBe("SERNAPESCA");
    expect(evidenceSourceLabel("mercadopublico", "https://www.mercadopublico.cl/")).toBe(
      "Mercado Público",
    );
  });
});

describe("prospectMessaging", () => {
  const base: LeadProspectDetailUi = {
    ...defaultLeadOriginFields,
    prospect_key: "x",
    organization_name: "Test Org",
    contact_name: null,
    email: "a@b.cl",
    domain: "b.cl",
    sector: "Lab",
    region: "RM",
    buyer_type: "laboratorio_privado",
    likely_need: "need A",
    product_angle: "centrífugas",
    evidence_url: "https://x.cl",
    evidence_note: "Nota evidencia",
    source: "sitio_oficial",
    final_score: 90,
    confidence: "alta",
    classification: "net_new_safe_review",
    spanish_message_angle: "Ángulo",
    risk_flags: "",
    block_or_review_reason: "",
    recommended_next_action: "Actuar",
    status: "net_new_safe_review",
    campaign_bucket: "private_lab",
    is_blocked: false,
  };

  it("does not duplicate product_angle in por qué importa", () => {
    const content = buildPorQueImporta(
      {
        ...base,
        likely_need: null,
        product_angle: "centrífugas; balances",
      },
      {
        table_available: true,
        data_source: "postgres_mirror",
        read_only: true,
        disclaimer: "",
        prospect: base,
        evidence: [],
        recommendation: {
          campaign_bucket: "private_lab",
          recommended_message_angle: null,
          recommended_next_action: null,
          why_this_lead: "centrífugas · balances",
          suggested_subject: null,
          suggested_body_preview: null,
          safety_note: null,
        },
        block_reasons: [],
      },
    );
    const joined = `${content.necesidadProbable} ${content.porQueInteresante}`;
    const angleCount = (joined.match(/centrífugas/gi) ?? []).length;
    expect(angleCount).toBeLessThanOrEqual(2);
    expect(content.queHaceEvidencia).toBe("Nota evidencia");
  });

  it("research_only without email has no message draft", () => {
    const preview = buildMessagePreview({
      ...base,
      organization_name: "BIOREN-UFRO",
      email: null,
      classification: "research_only_contact_needed",
      status: "research_needed",
    });
    expect(preview.kind).toBe("none");
    expect(preview.body).toBeUndefined();
    expect(preview.note).toMatch(/buscar responsable/i);
  });

  it("same_domain shows follow-up not cold email", () => {
    const preview = buildMessagePreview({
      ...base,
      classification: "same_domain_contacted_review",
      status: "same_domain_review",
    });
    expect(preview.kind).toBe("same_domain_followup");
    expect(preview.title).toMatch(/seguimiento/i);
    expect(preview.body).toMatch(/anteriormente habíamos enviado/i);
    expect(preview.body).not.toMatch(/breve llamada/i);
  });

  it("net_new shows softer ask without llamada default", () => {
    const preview = buildMessagePreview(base);
    expect(preview.kind).toBe("net_new");
    expect(preview.body).toMatch(/reposición, compra o cotización referencial/i);
    expect(preview.body).not.toMatch(/breve llamada/i);
  });

  it("blocked has no message", () => {
    const preview = buildMessagePreview({ ...base, is_blocked: true, classification: "already_contacted_block" });
    expect(preview.kind).toBe("none");
  });
});
