import { describe, expect, it } from "vitest";
import { translateApiMessage } from "./translateApi";

describe("translateApi", () => {
  it("translates sent-folder readiness warning", () => {
    const en =
      "Sent-folder history is not evaluated here (requires SQLite `emails` ingest). Use CLI/Streamlit preflight for full gate readiness.";
    const es = translateApiMessage(en);
    expect(es).toContain("carpeta Enviados");
    expect(es).not.toContain("Sent-folder");
  });

  it("translates readiness disclaimer", () => {
    const en =
      "Based on Postgres mirror tables only. Sent-folder ingest and live gates still use SQLite; sync lag may make this differ from Streamlit/CLI truth.";
    const es = translateApiMessage(en);
    expect(es).toContain("espejo Postgres");
    expect(es).not.toContain("Based on Postgres");
  });
});
