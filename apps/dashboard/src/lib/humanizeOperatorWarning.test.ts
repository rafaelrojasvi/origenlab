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

  it("humanizes Global MAX(date_iso) outlier warnings", () => {
    expect(
      humanizeOperatorWarning(
        "Global MAX(date_iso) outlier (2033-06-09T15:09:53+01:00) — prefer 2026-filtered freshness.",
      ),
    ).toBe(
      "Hay una fecha futura anómala en el archivo histórico. Para frescura diaria se usa la fecha filtrada de 2026.",
    );
  });

  it("humanizes FastLab not_contacted warnings", () => {
    expect(
      humanizeOperatorWarning(
        "FastLab (contacto@fastlab.cl): corrected to not_contacted; no Gmail Sent evidence; future outreach requires deliberate manual review.",
      ),
    ).toBe(
      "FastLab quedó marcado como no contactado porque no hay evidencia en Gmail Enviados. Revisar manualmente antes de contactar.",
    );
  });

  it("leaves unknown warnings unchanged", () => {
    const raw = "Quiteca: institutional caution — jorgepc@quiteca.cl contacted April 2026.";
    expect(humanizeOperatorWarning(raw)).toBe(raw);
  });
});
