import { describe, expect, it } from "vitest";
import { humanizeOperatorWarning } from "./humanizeOperatorWarning";

describe("humanizeOperatorWarning", () => {
  it("humanizes stale Postgres mirror sync", () => {
    expect(
      humanizeOperatorWarning("Postgres mirror last sync older than 24h (2026-06-01T00:00:00Z)."),
    ).toBe("El espejo Postgres no se ha sincronizado en más de 24h. Los datos pueden estar atrasados.");
  });

  it("humanizes missing daily-core manifest warnings", () => {
    expect(humanizeOperatorWarning("No daily-core run manifest found.")).toBe(
      "No hay daily-core registrado todavía. Ejecuta el refresco desde CLI si necesitas actualizar SQLite/reportes.",
    );
  });

  it("leaves unknown warnings unchanged", () => {
    const raw = "Quiteca: institutional caution — jorgepc@quiteca.cl contacted April 2026.";
    expect(humanizeOperatorWarning(raw)).toBe(raw);
  });
});
