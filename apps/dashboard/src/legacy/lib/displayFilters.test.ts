import { describe, expect, it } from "vitest";
import type { ContactRow, OrganizationRow } from "../api/types";
import {
  filterContactsForDisplay,
  isConsumerEmailDomain,
  isInternalEmail,
  isInternalOrganizationDomain,
  selectOrganizationsForDisplay,
} from "./displayFilters";

describe("displayFilters", () => {
  it("hides internal contact emails", () => {
    expect(isInternalEmail("contacto@origenlab.cl")).toBe(true);
    expect(isInternalEmail("Lab@origenlab.cl")).toBe(true);
    expect(isInternalEmail("cliente@universidad.cl")).toBe(false);
  });

  it("filterContactsForDisplay excludes internal and caps rows", () => {
    const items: ContactRow[] = [
      { email: "contacto@origenlab.cl" },
      { email: "a@lab.cl" },
      { email: "b@corp.cl" },
      { email: "c@corp.cl" },
      { email: "d@corp.cl" },
      { email: "e@corp.cl" },
      { email: "f@corp.cl" },
    ];
    const shown = filterContactsForDisplay(items, 3);
    expect(shown.map((r) => r.email)).toEqual(["a@lab.cl", "b@corp.cl", "c@corp.cl"]);
  });

  it("partitions consumer email domains in organizations", () => {
    const items: OrganizationRow[] = [
      { domain: "universidad.cl" },
      { domain: "gmail.com" },
      { domain: "origenlab.cl" },
      { domain: "hotmail.com" },
      { domain: "empresa.cl" },
    ];
    const { primary, consumer } = selectOrganizationsForDisplay(items, 5);
    expect(primary.map((o) => o.domain)).toEqual(["universidad.cl", "empresa.cl"]);
    expect(consumer.map((o) => o.domain)).toEqual(["gmail.com", "hotmail.com"]);
    expect(isInternalOrganizationDomain("origenlab.cl")).toBe(true);
  });

  it("detects consumer domains", () => {
    expect(isConsumerEmailDomain("outlook.com")).toBe(true);
    expect(isConsumerEmailDomain("empresa.cl")).toBe(false);
  });
});
