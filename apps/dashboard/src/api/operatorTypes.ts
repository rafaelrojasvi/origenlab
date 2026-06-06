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
