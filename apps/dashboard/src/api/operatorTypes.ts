/** Types for apps/api operator plane (GET /health, GET /operator/status). */

export type ApiBackend = "sqlite" | "postgres";

export interface HealthResponse {
  ok: boolean;
  service: string;
  mode: string;
  backend: ApiBackend;
  postgres_configured: boolean;
}

export interface OperatorStatusResponse {
  verdict: string;
  sqlite_path: string;
  campaign_mode: string | null;
  operator_focus: string | null;
  outbound_readiness: string;
  warnings: string[];
}

export interface TodayPanelData {
  health: HealthResponse;
  operator: OperatorStatusResponse;
}
