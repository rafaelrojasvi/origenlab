import type { OperatorAutomationStatus } from "../api/operatorTypes";
import {
  chilecompraAutomationResultLabel,
  formatAutomationTimeShort,
} from "./automationHealthLabels";
import { formatAutomationFreshnessAgeLabel } from "./automationFreshness";

export type AutomationRunTone = "ok" | "attention" | "blocked" | "muted";

export type AutomationRunSummaryRow = {
  id: string;
  label: string;
  tone: AutomationRunTone;
  primary: string;
  secondary: string | null;
  finishedAt: string | null;
  startedAt: string | null;
};

export const AUTOMATION_RUN_TONE_CLASS: Record<AutomationRunTone, string> = {
  ok: "border-emerald-200 bg-emerald-50/80 text-emerald-950",
  attention: "border-amber-200 bg-amber-50/80 text-amber-950",
  blocked: "border-red-200 bg-red-50/80 text-red-950",
  muted: "border-slate-200 bg-slate-50/80 text-slate-700",
};

const SUCCESS_RESULTS = new Set(["success", "no_change", "refreshed"]);
const FAILURE_RESULTS = new Set([
  "mirror_failed",
  "daily_core_failed",
  "build_failed",
  "ticket_missing",
  "failed",
  "error",
]);

function parseTimestamp(value: string | null | undefined): number | null {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Date.parse(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function pickFinishedAt(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return null;
}

function compactResultMeta(
  result: string | null | undefined,
  options: {
    lockLive?: boolean;
    paused?: boolean;
    consecutiveFailures?: number;
    cooldownRemainingSeconds?: number;
  } = {},
): { primary: string; tone: AutomationRunTone } {
  if (options.lockLive) {
    return { primary: "en curso", tone: "attention" };
  }
  if (options.paused) {
    return { primary: "pausado", tone: "muted" };
  }
  const failures = options.consecutiveFailures ?? 0;
  if (failures > 0) {
    return { primary: "falló", tone: "blocked" };
  }
  if ((options.cooldownRemainingSeconds ?? 0) > 0) {
    return { primary: "en cooldown", tone: "attention" };
  }
  const normalized = result?.trim().toLowerCase() ?? "";
  if (!normalized) {
    return { primary: "sin dato", tone: "muted" };
  }
  if (SUCCESS_RESULTS.has(normalized)) {
    return { primary: "éxito", tone: "ok" };
  }
  if (normalized === "cooldown") {
    return { primary: "en cooldown", tone: "attention" };
  }
  if (FAILURE_RESULTS.has(normalized) || normalized.includes("fail")) {
    return { primary: "falló", tone: "blocked" };
  }
  if (normalized === "mail_dirty") {
    return { primary: "pendiente", tone: "attention" };
  }
  if (normalized === "lock_live") {
    return { primary: "en curso", tone: "attention" };
  }
  return { primary: normalized, tone: "attention" };
}

function formatRunTiming(
  finishedAt: string | null,
  startedAt: string | null,
  nowMs: number,
): string {
  if (finishedAt) {
    const finishedTs = parseTimestamp(finishedAt);
    const ageLabel = formatAutomationFreshnessAgeLabel(
      finishedTs != null ? nowMs - finishedTs : null,
    );
    const shortTime = formatAutomationTimeShort(finishedAt);
    if (shortTime !== "—" && ageLabel !== "sin dato") {
      return `fin ${shortTime} · ${ageLabel}`;
    }
    if (ageLabel !== "sin dato") {
      return `fin ${ageLabel}`;
    }
  }
  if (startedAt) {
    const shortTime = formatAutomationTimeShort(startedAt);
    return shortTime !== "—" ? `inicio ${shortTime}` : "sin dato";
  }
  return "sin dato";
}

function appendFailuresHint(base: string, failures: number): string {
  if (failures <= 0) {
    return base;
  }
  return `${base} · ${failures} falla${failures === 1 ? "" : "s"}`;
}

function buildGmailRunRow(
  status: OperatorAutomationStatus,
  nowMs: number,
): AutomationRunSummaryRow {
  const mail = status.mail_auto_refresh;
  const { primary, tone } = compactResultMeta(mail.last_result, {
    lockLive: mail.lock_live,
    paused: mail.paused,
    consecutiveFailures: mail.consecutive_failures,
  });
  const finishedAt = pickFinishedAt(mail.last_run_finished_at, mail.last_successful_refresh_at);
  const startedAt = mail.last_run_started_at?.trim() || null;
  const timing = formatRunTiming(finishedAt, startedAt, nowMs);
  const secondary = appendFailuresHint(timing, mail.consecutive_failures);
  return {
    id: "gmail-sqlite",
    label: "Gmail → SQLite",
    tone,
    primary,
    secondary,
    finishedAt,
    startedAt,
  };
}

function buildMirrorLoopRunRow(
  status: OperatorAutomationStatus,
  nowMs: number,
): AutomationRunSummaryRow {
  const mirror = status.dashboard_auto_mirror;
  const { primary, tone } = compactResultMeta(mirror.last_result, {
    lockLive: mirror.lock_live,
    paused: mirror.paused,
    consecutiveFailures: mirror.consecutive_failures,
    cooldownRemainingSeconds: mirror.cooldown_remaining_seconds,
  });
  const finishedAt = pickFinishedAt(
    mirror.last_run_finished_at,
    mirror.last_successful_mirror_at,
  );
  const startedAt = mirror.last_run_started_at?.trim() || null;
  const timing = formatRunTiming(finishedAt, startedAt, nowMs);
  const cooldownHint =
    mirror.cooldown_remaining_seconds > 0
      ? `cooldown ${mirror.cooldown_remaining_seconds}s`
      : null;
  const secondary = appendFailuresHint(
    cooldownHint ? `${timing} · ${cooldownHint}` : timing,
    mirror.consecutive_failures,
  );
  return {
    id: "sqlite-dashboard",
    label: "SQLite → Dashboard",
    tone,
    primary,
    secondary,
    finishedAt,
    startedAt,
  };
}

function buildChilecompraRunRow(
  status: OperatorAutomationStatus,
  nowMs: number,
): AutomationRunSummaryRow {
  const chilecompra = status.chilecompra_equipment_auto_refresh;
  if (!chilecompra?.state_exists) {
    return {
      id: "chilecompra",
      label: "ChileCompra",
      tone: "muted",
      primary: "sin dato",
      secondary: null,
      finishedAt: null,
      startedAt: null,
    };
  }
  const { primary, tone } = compactResultMeta(chilecompra.last_result, {
    lockLive: chilecompra.lock_live,
    consecutiveFailures: chilecompra.consecutive_failures,
  });
  const finishedAt = pickFinishedAt(
    chilecompra.last_run_finished_at,
    chilecompra.last_successful_refresh_at,
    chilecompra.last_successful_publish_at,
  );
  const startedAt = chilecompra.last_run_started_at?.trim() || null;
  const timing = formatRunTiming(finishedAt, startedAt, nowMs);
  const detailParts: string[] = [timing];
  const rowCount = chilecompra.published_rows ?? chilecompra.output_rows;
  if (rowCount != null) {
    detailParts.push(`${rowCount} filas`);
  }
  if (chilecompra.detail_error_count != null) {
    detailParts.push(`${chilecompra.detail_error_count} errores detalle`);
  }
  if (chilecompra.last_error?.trim()) {
    detailParts.push("con error");
  }
  const secondary = appendFailuresHint(detailParts.join(" · "), chilecompra.consecutive_failures);
  const displayPrimary =
    primary === "sin dato" && chilecompra.last_result
      ? chilecompraAutomationResultLabel(chilecompra.last_result).toLowerCase()
      : primary;
  return {
    id: "chilecompra",
    label: "ChileCompra",
    tone,
    primary: displayPrimary,
    secondary,
    finishedAt,
    startedAt,
  };
}

function buildPostgresSyncRunRow(
  status: OperatorAutomationStatus,
  nowMs: number,
): AutomationRunSummaryRow {
  const sync = status.dashboard_mirror_sync;
  if (!sync) {
    return {
      id: "postgres-sync",
      label: "Espejo Postgres",
      tone: "muted",
      primary: "sin dato",
      secondary: null,
      finishedAt: null,
      startedAt: null,
    };
  }
  const normalizedStatus = sync.status?.trim().toLowerCase() ?? "";
  let primary = "sin dato";
  let tone: AutomationRunTone = "muted";
  if (normalizedStatus === "success") {
    primary = "éxito";
    tone = "ok";
  } else if (normalizedStatus === "missing_table") {
    primary = "sin tabla";
    tone = "muted";
  } else if (sync.error_message?.trim() || normalizedStatus.includes("fail")) {
    primary = "falló";
    tone = "blocked";
  } else if (normalizedStatus) {
    primary = normalizedStatus;
    tone = "attention";
  }
  const finishedAt = sync.finished_at?.trim() || null;
  const startedAt = sync.started_at?.trim() || null;
  const timing = formatRunTiming(finishedAt, startedAt, nowMs);
  const detailParts: string[] = [timing];
  if (sync.latest_sync_id != null) {
    detailParts.push(`sync #${sync.latest_sync_id}`);
  }
  if (sync.elapsed_seconds != null) {
    detailParts.push(`${sync.elapsed_seconds}s`);
  }
  if (sync.error_message?.trim()) {
    detailParts.push("con error");
  }
  return {
    id: "postgres-sync",
    label: "Espejo Postgres",
    tone,
    primary,
    secondary: detailParts.join(" · "),
    finishedAt,
    startedAt,
  };
}

export function buildAutomationRunSummary(
  status: OperatorAutomationStatus,
  options?: { now?: Date },
): AutomationRunSummaryRow[] {
  const nowMs = (options?.now ?? new Date()).getTime();
  return [
    buildGmailRunRow(status, nowMs),
    buildMirrorLoopRunRow(status, nowMs),
    buildChilecompraRunRow(status, nowMs),
    buildPostgresSyncRunRow(status, nowMs),
  ];
}
