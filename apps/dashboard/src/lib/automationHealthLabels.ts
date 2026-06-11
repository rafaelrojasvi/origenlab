import type { OperatorAutomationStatus } from "../api/operatorTypes";
import { formatDashboardDateTime } from "./dashboardDateFormat";

export function automationVerdictLabel(verdict: string): string {
  switch (verdict) {
    case "healthy":
      return "Automatización al día";
    case "attention":
      return "Requiere atención";
    case "blocked":
      return "Bloqueado";
    default:
      return verdict;
  }
}

export function automationRecommendedActionLabel(action: string): string {
  switch (action) {
    case "none":
      return "Sin acción requerida";
    case "run_auto_mirror_dashboard":
      return "Publicar espejo dashboard";
    case "wait_for_mail_quiet_window":
      return "Esperar ventana de calma de Gmail";
    case "wait_for_mirror_cooldown":
      return "Esperar cooldown del espejo";
    case "inspect_failed_daily_core":
      return "Revisar daily-core";
    case "wait_for_running_mail_refresh":
      return "Esperar refresh de Gmail en curso";
    case "wait_for_running_mirror_refresh":
      return "Esperar publicación del espejo en curso";
    case "resume_or_leave_paused":
      return "Automatización en pausa";
    case "inspect_logs":
      return "Revisar logs";
    case "create_missing_state_by_running_dry_run":
      return "Publicar snapshot o revisar localmente";
    case "clear_stale_lock_after_manual_review":
      return "Revisar lock obsoleto manualmente";
    default:
      return action;
  }
}

export function automationVerdictTone(verdict: string): {
  banner: string;
  badge: string;
} {
  switch (verdict) {
    case "healthy":
      return {
        banner: "border-emerald-200 bg-emerald-50/80",
        badge: "bg-emerald-100 text-emerald-900",
      };
    case "attention":
      return {
        banner: "border-amber-200 bg-amber-50/80",
        badge: "bg-amber-100 text-amber-900",
      };
    case "blocked":
      return {
        banner: "border-red-200 bg-red-50/80",
        badge: "bg-red-100 text-red-900",
      };
    default:
      return {
        banner: "border-slate-200 bg-slate-50/80",
        badge: "bg-slate-100 text-slate-800",
      };
  }
}

export function formatAutomationTimestamp(ts: string | null | undefined): string {
  return formatDashboardDateTime(ts);
}

export const AUTOMATION_MISSING_STATE_PRIMARY =
  "Snapshot local no publicado";

export const AUTOMATION_SNAPSHOT_PUBLISHED_PRIMARY =
  "Snapshot local publicado";

function pickLatestAutomationTimestamp(
  values: Array<string | null | undefined>,
): string | null {
  let best: { iso: string; ts: number } | null = null;
  for (const value of values) {
    const trimmed = value?.trim();
    if (!trimmed) continue;
    const ts = Date.parse(trimmed);
    if (!Number.isFinite(ts)) continue;
    if (!best || ts > best.ts) {
      best = { iso: trimmed, ts };
    }
  }
  return best?.iso ?? null;
}

export function buildAutomationSnapshotSummary(
  status: OperatorAutomationStatus,
): string | null {
  if (status.source === "postgres_snapshot") {
    const parts: string[] = [];
    if (status.snapshot_stale) {
      parts.push("Snapshot publicado, pero desactualizado");
    } else {
      parts.push(AUTOMATION_SNAPSHOT_PUBLISHED_PRIMARY);
    }
    parts.push("Fuente: espejo Postgres");
    if (status.snapshot_updated_at) {
      parts.push(`Actualizado: ${formatAutomationTimestamp(status.snapshot_updated_at)}`);
    }
    return parts.join(" · ");
  }
  if (operatorAutomationStatePartiallyMissing(status)) {
    return null;
  }
  const lastUpdate = pickLatestAutomationTimestamp([
    status.generated_at_utc,
    status.daily_core.generated_at_utc,
    status.mail_auto_refresh.last_successful_refresh_at,
    status.dashboard_auto_mirror.last_successful_mirror_at,
  ]);
  const parts = [AUTOMATION_SNAPSHOT_PUBLISHED_PRIMARY];
  if (lastUpdate) {
    parts.push(`última actualización ${formatAutomationTimestamp(lastUpdate)}`);
  }
  if (status.daily_core.exists) {
    parts.push("daily-core visible");
  }
  if (status.dashboard_auto_mirror.state_exists) {
    parts.push("mirror visible");
  }
  return parts.join(" · ");
}

export function mailLoopStatusLabel(status: OperatorAutomationStatus): string {
  if (status.mail_auto_refresh.dirty || status.mail_auto_refresh.pending) {
    return "pendiente";
  }
  return "limpio";
}

export function mirrorLoopStatusLabel(status: OperatorAutomationStatus): boolean | null {
  return status.dashboard_auto_mirror.mirror_matches_daily_core;
}

export const AUTOMATION_MISSING_STATE_HELP =
  "El API en producción no ve los archivos de estado locales del operador. La validación local puede estar LISTO aunque este panel muestre atención. Publique un snapshot al espejo o revise el estado en el servidor.";

export function operatorAutomationStatePartiallyMissing(
  status: OperatorAutomationStatus,
): boolean {
  if (status.source === "postgres_snapshot") {
    return false;
  }
  return (
    status.daily_core.exists === false ||
    !status.mail_auto_refresh.state_exists ||
    !status.dashboard_auto_mirror.state_exists
  );
}

export function formatAutomationBool(value: boolean | null | undefined): string {
  if (value === true) return "sí";
  if (value === false) return "no";
  return "—";
}
