import { describe, expect, it } from "vitest";
import { formatMirrorLoadError, humanizeApiError } from "./humanizeApiError";
import { OperatorApiError } from "../api/operatorClient";

describe("humanizeApiError", () => {
  it("maps Postgres URL not configured errors", () => {
    expect(
      humanizeApiError('{"detail":"Postgres audit requested but no Postgres URL resolved"}'),
    ).toBe(
      "El espejo Postgres no está configurado en este entorno. Esta vista de espejo puede estar vacía, pero Hoy y las colas SQLite siguen disponibles.",
    );
  });

  it("maps ORIGENLAB_POSTGRES_URL hints", () => {
    expect(humanizeApiError("Set ORIGENLAB_POSTGRES_URL before mirror reads")).toContain(
      "El espejo Postgres no está configurado",
    );
  });

  it("maps ALEMBIC_DATABASE_URL hints", () => {
    expect(humanizeApiError("Missing ALEMBIC_DATABASE_URL for mirror")).toContain(
      "El espejo Postgres no está configurado",
    );
  });

  it("leaves unknown errors unchanged", () => {
    const raw = "Unexpected upstream failure";
    expect(humanizeApiError(raw)).toBe(raw);
  });
});

describe("formatMirrorLoadError", () => {
  it("returns human message and technical detail for mirror unavailable", () => {
    const raw = '{"detail":"Postgres audit requested but no Postgres URL resolved"}';
    const formatted = formatMirrorLoadError(
      "Catálogo",
      new OperatorApiError(raw, 503),
    );
    expect(formatted.message).toContain("El espejo Postgres no está configurado");
    expect(formatted.detail).toContain("API 503");
    expect(formatted.detail).toContain(raw);
  });
});
