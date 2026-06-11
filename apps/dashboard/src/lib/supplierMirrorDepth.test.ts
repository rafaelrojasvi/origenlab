import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  buildSupplierMirrorDepthSummary,
  supplierGmailDetectedLabel,
  supplierMirrorCaseLabel,
} from "./supplierMirrorDepth";

function row(grouped: number): WarmCaseItem {
  return {
    case_id: "x",
    last_email_id: 1,
    last_seen_at: null,
    account_name: "IKA",
    contact_email: "a@ika.net.br",
    subject: "thread",
    category: "supplier_quote_received",
    status: "open",
    next_action: "",
    equipment_signal: "",
    snippet: "",
    gmail_url: null,
    grouped_email_count: grouped,
  };
}

describe("supplierMirrorDepth", () => {
  it("labels mirror cases in espejo", () => {
    expect(supplierMirrorCaseLabel(1)).toBe("1 caso en espejo");
    expect(supplierMirrorCaseLabel(2)).toBe("2 casos en espejo");
  });

  it("shows grouped Gmail depth when available", () => {
    expect(supplierGmailDetectedLabel([row(7)])).toBe("7+ mensajes Gmail detectados");
    expect(buildSupplierMirrorDepthSummary([row(7)])).toBe(
      "1 caso en espejo · 7+ mensajes Gmail detectados",
    );
  });

  it("omits Gmail depth when only one message grouped", () => {
    expect(buildSupplierMirrorDepthSummary([row(1)])).toBe("1 caso en espejo");
  });
});
