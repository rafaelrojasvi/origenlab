const esNumber = new Intl.NumberFormat("es-CL");

export function formatClp(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${esNumber.format(value)} CLP`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return esNumber.format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 16);
  return d.toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
}

export function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    ready: "Listo",
    ready_with_warnings: "Listo con advertencias",
    not_ready: "No listo",
    unknown: "Desconocido",
  };
  return map[verdict] ?? verdict;
}
