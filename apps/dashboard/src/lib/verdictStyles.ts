export function verdictTone(verdict: string): {
  banner: string;
  badge: string;
  label: string;
} {
  const v = verdict.toUpperCase();
  if (v === "READY") {
    return {
      banner: "border-emerald-200 bg-emerald-50 text-emerald-950",
      badge: "bg-emerald-600 text-white",
      label: "READY",
    };
  }
  if (v === "CAUTION") {
    return {
      banner: "border-amber-200 bg-amber-50 text-amber-950",
      badge: "bg-amber-600 text-white",
      label: "CAUTION",
    };
  }
  if (v === "BLOCKED") {
    return {
      banner: "border-red-200 bg-red-50 text-red-950",
      badge: "bg-red-700 text-white",
      label: "BLOCKED",
    };
  }
  return {
    banner: "border-slate-200 bg-slate-50 text-slate-900",
    badge: "bg-slate-600 text-white",
    label: verdict || "UNKNOWN",
  };
}

export function backendLabel(backend: string): string {
  return backend === "postgres" ? "Postgres mirror" : "SQLite";
}

export function backendChipClass(backend: string): string {
  return backend === "postgres"
    ? "bg-sky-100 text-sky-900 ring-sky-200"
    : "bg-slate-100 text-slate-800 ring-slate-200";
}
