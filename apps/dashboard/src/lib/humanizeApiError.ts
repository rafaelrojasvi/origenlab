import { OperatorApiError } from "../api/operatorClient";

const POSTGRES_MIRROR_UNAVAILABLE =
  "El espejo Postgres no está configurado en este entorno. Esta vista de espejo puede estar vacía, pero Hoy y las colas SQLite siguen disponibles.";

function isPostgresMirrorUnavailable(text: string): boolean {
  return (
    text.includes("Postgres audit requested but no Postgres URL resolved") ||
    text.includes("ORIGENLAB_POSTGRES_URL") ||
    text.includes("ALEMBIC_DATABASE_URL")
  );
}

/** Display-only Spanish copy for known mirror/API error strings. */
export function humanizeApiError(message: string): string {
  const text = message.trim();
  if (!text) {
    return message;
  }
  if (isPostgresMirrorUnavailable(text)) {
    return POSTGRES_MIRROR_UNAVAILABLE;
  }
  return message;
}

export function mirrorLoadErrorFromMessage(
  label: string,
  rawMessage: string,
  status?: number,
): { message: string; detail: string | null } {
  const human = humanizeApiError(rawMessage);
  if (human !== rawMessage) {
    const detail =
      status != null ? `${label} (API ${status}): ${rawMessage}` : `${label}: ${rawMessage}`;
    return { message: human, detail };
  }
  if (status != null) {
    return { message: `${label} (API ${status}): ${rawMessage}`, detail: null };
  }
  return { message: `${label}: ${rawMessage}`, detail: null };
}

export function formatMirrorLoadError(
  label: string,
  e: unknown,
): { message: string; detail: string | null } {
  if (e instanceof OperatorApiError) {
    return mirrorLoadErrorFromMessage(label, e.message, e.status);
  }
  if (e instanceof Error) {
    return mirrorLoadErrorFromMessage(label, e.message);
  }
  return { message: `${label}: error desconocido`, detail: null };
}
