/** Types for apps/api operator plane (GET /health, GET /operator/status). */

export type ApiBackend = "sqlite" | "postgres";

export interface HealthResponse {
  ok: boolean;
  service: string;
  mode: string;
  backend: ApiBackend;
  postgres_configured: boolean;
}

export interface DailyCoreRunStatus {
  path?: string;
  exists: boolean;
  loaded?: boolean;
  parse_error?: boolean;
  schema_version?: number;
  workflow?: string;
  generated_at_utc?: string;
  status?: string;
  returncode?: number;
  step_count?: number;
  last_step?: string;
  send_approval?: boolean;
  postgres_mirror?: string;
}

export interface OperatorStatusResponse {
  verdict: string;
  sqlite_path: string;
  campaign_mode: string | null;
  operator_focus: string | null;
  outbound_readiness: string;
  warnings: string[];
  daily_core_run: DailyCoreRunStatus;
}

export interface TodayPanelData {
  health: HealthResponse;
  operator: OperatorStatusResponse;
}

export interface DailyCoreAutomationStatus {
  exists?: boolean;
  status?: string | null;
  returncode?: number | null;
  generated_at_utc?: string | null;
  age_seconds?: number | null;
  steps?: number;
  parse_error?: string | null;
}

export interface MailAutoRefreshStatus {
  state_exists: boolean;
  paused: boolean;
  lock_live: boolean;
  dirty: boolean;
  pending: boolean;
  last_result?: string | null;
  last_change_seen_at?: string | null;
  last_successful_refresh_at?: string | null;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  last_seen_inbox_total?: number | null;
  last_seen_sent_total?: number | null;
  pending_inbox_total?: number | null;
  pending_sent_total?: number | null;
  consecutive_failures: number;
}

export interface DashboardAutoMirrorStatus {
  state_exists: boolean;
  paused: boolean;
  lock_live: boolean;
  last_result?: string | null;
  last_successful_mirror_at?: string | null;
  last_mirrored_daily_core_generated_at?: string | null;
  mirror_matches_daily_core: boolean | null;
  cooldown_seconds: number;
  cooldown_remaining_seconds: number;
  consecutive_failures: number;
}

export interface OperatorAutomationStatus {
  generated_at_utc: string;
  active_current_dir: string;
  verdict: string;
  daily_core: DailyCoreAutomationStatus;
  mail_auto_refresh: MailAutoRefreshStatus;
  dashboard_auto_mirror: DashboardAutoMirrorStatus;
  cron: { note: string };
  recommended_action: string;
  warnings: string[];
  source?: "postgres_snapshot" | "filesystem_active_current" | null;
  snapshot_updated_at?: string | null;
  snapshot_stale?: boolean | null;
}
