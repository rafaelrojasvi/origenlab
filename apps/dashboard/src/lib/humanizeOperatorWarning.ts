/** Display-only Spanish copy for known operator warning strings (API text unchanged). */

export function humanizeOperatorWarning(warning: string): string {
  const text = warning.trim();
  if (!text) {
    return warning;
  }

  if (/Postgres mirror last sync older than 24h/i.test(text)) {
    return "El espejo Postgres no se ha sincronizado en más de 24h. Los datos pueden estar atrasados.";
  }

  if (/Global MAX\(date_iso\) outlier/i.test(text)) {
    return "Hay una fecha futura anómala en el archivo histórico. Para frescura diaria se usa la fecha filtrada de 2026.";
  }

  if (/FastLab/i.test(text) && /corrected to not_contacted/i.test(text)) {
    return "FastLab quedó marcado como no contactado porque no hay evidencia en Gmail Enviados. Revisar manualmente antes de contactar.";
  }

  if (
    /daily[- ]core/i.test(text) &&
    (/manifest|no run|missing|not registered|sin ejecución|no daily/i.test(text) ||
      /daily_core_run/i.test(text))
  ) {
    return "No hay daily-core registrado todavía. Ejecuta el refresco desde CLI si necesitas actualizar SQLite/reportes.";
  }

  return warning;
}
