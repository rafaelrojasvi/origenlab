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

const USEFUL_SUCCESS_RESULTS = new Set(["success", "refreshed"]);
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
    kind?: "mail" | "mirror" | "chilecompra" | "generic";
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
  if (normalized === "no_change") {
    return { primary: "sin cambios", tone: "ok" };
  }
  if (normalized === "already_mirrored") {
    return { primary: "ya sincronizado", tone: "ok" };
  }
  if (normalized === "cooldown") {
    return { primary: "en cooldown", tone: "attention" };
  }
  if (FAILURE_RESULTS.has(normalized) || normalized.includes("fail")) {
    return { primary: "falló", tone: "blocked" };
  }
  if (normalized === "refreshed" && options.kind === "chilecompra") {
    return { primary: "actualizado", tone: "ok" };
  }
  if (USEFUL_SUCCESS_RESULTS.has(normalized)) {
    return { primary: "éxito", tone: "ok" };
  }
  if (normalized === "mail_dirty") {
    return { primary: "pendiente", tone: "attention" };
  }
  if (normalized === "lock_live") {
    return { primary: "en curso", tone: "attention" };
  }
  return { primary: normalized, tone: "attention" };
}

function formatLastAttemptLine(finishedAt: string | null, nowMs: number): string | null {
  if (!finishedAt?.trim()) {
    return null;
  }
  const finishedTs = parseTimestamp(finishedAt);
  const ageLabel = formatAutomationFreshnessAgeLabel(
    finishedTs != null ? nowMs - finishedTs : null,
  );
  const shortTime = formatAutomationTimeShort(finishedAt);
  if (shortTime !== "—" && ageLabel !== "sin dato") {
    return `último intento: fin ${shortTime} · ${ageLabel}`;
  }
  if (ageLabel !== "sin dato") {
    return `último intento: ${ageLabel}`;
  }
  return null;
}

function formatUsefulTimestampLine(
  label: string,
  timestamp: string | null,
  nowMs: number,
): string | null {
  if (!timestamp?.trim()) {
    return null;
  }
  const ts = parseTimestamp(timestamp);
  const ageLabel = formatAutomationFreshnessAgeLabel(ts != null ? nowMs - ts : null);
  if (ageLabel === "sin dato") {
    return null;
  }
  return `${label}: ${ageLabel}`;
}

function joinSecondaryParts(parts: Array<string | null>, failures: number): string | null {
  const filtered = parts.filter((part): part is string => Boolean(part));
  if (failures > 0) {
    filtered.push(`${failures} falla${failures === 1 ? "" : "s"}`);
  }
  return filtered.length ? filtered.join(" · ") : null;
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
    kind: "mail",
  });
  const attemptFinishedAt = mail.last_run_finished_at?.trim() || null;
  const usefulRefreshAt = mail.last_successful_refresh_at?.trim() || null;
  const finishedAt = pickFinishedAt(attemptFinishedAt, usefulRefreshAt);
  const startedAt = mail.last_run_started_at?.trim() || null;
  const secondaryParts: Array<string | null> = [
    formatLastAttemptLine(attemptFinishedAt, nowMs),
  ];
  if (usefulRefreshAt && usefulRefreshAt !== attemptFinishedAt) {
    secondaryParts.push(
      formatUsefulTimestampLine("último refresh útil", usefulRefreshAt, nowMs),
    );
  } else if (!attemptFinishedAt && usefulRefreshAt) {
    secondaryParts.push(
      formatUsefulTimestampLine("último refresh útil", usefulRefreshAt, nowMs),
    );
  }
  return {
    id: "gmail-sqlite",
    label: "Gmail → SQLite",
    tone,
    primary,
    secondary: joinSecondaryParts(secondaryParts, mail.consecutive_failures),
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
    kind: "mirror",
  });
  const attemptFinishedAt = mirror.last_run_finished_at?.trim() || null;
  const appliedMirrorAt = mirror.last_successful_mirror_at?.trim() || null;
  const finishedAt = pickFinishedAt(attemptFinishedAt, appliedMirrorAt);
  const startedAt = mirror.last_run_started_at?.trim() || null;
  const secondaryParts: Array<string | null> = [
    formatLastAttemptLine(attemptFinishedAt, nowMs),
  ];
  if (appliedMirrorAt && appliedMirrorAt !== attemptFinishedAt) {
    secondaryParts.push(
      formatUsefulTimestampLine("último espejo aplicado", appliedMirrorAt, nowMs),
    );
  } else if (!attemptFinishedAt && appliedMirrorAt) {
    secondaryParts.push(
      formatUsefulTimestampLine("último espejo aplicado", appliedMirrorAt, nowMs),
    );
  }
  if (mirror.cooldown_remaining_seconds > 0) {
    secondaryParts.push(`cooldown ${mirror.cooldown_remaining_seconds}s`);
  }
  return {
    id: "sqlite-dashboard",
    label: "SQLite → Dashboard",
    tone,
    primary,
    secondary: joinSecondaryParts(secondaryParts, mirror.consecutive_failures),
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
    kind: "chilecompra",
  });
  const finishedAt = pickFinishedAt(
    chilecompra.last_run_finished_at,
    chilecompra.last_successful_refresh_at,
    chilecompra.last_successful_publish_at,
  );
  const startedAt = chilecompra.last_run_started_at?.trim() || null;
  const attemptFinishedAt = chilecompra.last_run_finished_at?.trim() || null;
  const detailParts: Array<string | null> = [formatLastAttemptLine(attemptFinishedAt, nowMs)];
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
  const secondary = joinSecondaryParts(detailParts, chilecompra.consecutive_failures);
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
  const detailParts: Array<string | null> = [formatLastAttemptLine(finishedAt, nowMs)];
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
    secondary: joinSecondaryParts(detailParts, 0),
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
