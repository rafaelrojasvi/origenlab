/** Format helpers for redacted commercial deal mirror UI. */

export function formatClp(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMarginPct(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatEurDecimal(value: string | null | undefined): string {
  const s = (value ?? "").trim();
  if (!s) {
    return "—";
  }
  return `EUR ${s}`;
}

export function formatUpdatedAt(value: string | null | undefined): string {
  const s = (value ?? "").trim();
  if (!s) {
    return "—";
  }
  return s.length > 19 ? s.slice(0, 19) : s;
}

export function formatBlockersPreview(blockers: string[]): string {
  if (!blockers.length) {
    return "—";
  }
  const joined = blockers.join(" · ");
  if (joined.length <= 120) {
    return joined;
  }
  return `${joined.slice(0, 117)}…`;
}
