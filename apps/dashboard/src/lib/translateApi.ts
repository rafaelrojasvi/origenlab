/** Map known English API copy to Spanish for the dashboard UI. */

const EXACT: Record<string, string> = {
  "Based on Postgres mirror tables only. Sent-folder ingest and live gates still use SQLite; sync lag may make this differ from Streamlit/CLI truth.":
    "Basado solo en tablas espejo Postgres. El ingest de Enviados y las compuertas en vivo siguen usando SQLite; el desfase de sincronización puede hacer que difiera de Streamlit o la CLI.",
  "Sent-folder history is not evaluated here (requires SQLite `emails` ingest). Use CLI/Streamlit preflight for full gate readiness.":
    "El historial de la carpeta Enviados no se evalúa aquí (requiere ingest SQLite de `emails`). Use el preflight de CLI o Streamlit para la preparación completa de compuertas.",
};

const PARTIAL: [RegExp, string][] = [
  [/Postgres table missing/gi, "Tabla Postgres ausente"],
  [/run Alembic/gi, "ejecute Alembic"],
  [/Tier A sync/gi, "sincronización Tier A"],
  [/run mart rebuild \+ sync/gi, "reconstruya el mart y sincronice"],
  [/sync from SQLite/gi, "sincronice desde SQLite"],
  [/is empty/gi, "está vacía"],
  [/eventually consistent/gi, "consistencia eventual"],
];

export function translateApiMessage(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  if (EXACT[trimmed]) return EXACT[trimmed];
  let out = trimmed;
  for (const [pattern, replacement] of PARTIAL) {
    out = out.replace(pattern, replacement);
  }
  return out;
}

export function translateApiMessages(messages: string[]): string[] {
  return messages.map(translateApiMessage);
}
