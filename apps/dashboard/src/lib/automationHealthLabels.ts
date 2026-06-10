import type { OperatorAutomationStatus } from "../api/operatorTypes";

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
      return "Ejecutar dry-run para crear estado";
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
  if (!ts) return "—";
  return ts;
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
