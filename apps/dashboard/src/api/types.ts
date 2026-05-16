export type DataScope = "canonical" | "archive";

export interface DashboardSummary {
  contact_count: number;
  organization_count: number;
  opportunity_signal_count: number;
  email_suppression_count: number;
  domain_suppression_count: number;
  outreach_state_count: number;
  scope: DataScope;
  scope_available: boolean;
  scope_note: string;
  eventually_consistent: boolean;
  data_source: string;
  archive_mirror_counts?: Record<string, number>;
}

export interface ContactRow {
  email: string;
  contact_name_best?: string | null;
  domain?: string | null;
  organization_name_guess?: string | null;
  last_seen_at?: string | null;
  total_emails?: number | null;
}

export interface OrganizationRow {
  domain: string;
  organization_name_guess?: string | null;
  total_contacts?: number | null;
  last_seen_at?: string | null;
}

export interface PaginatedContacts {
  items: ContactRow[];
  total: number;
  scope: DataScope;
  scope_note: string;
}

export interface PaginatedOrganizations {
  items: OrganizationRow[];
  total: number;
  scope: DataScope;
  scope_note: string;
}

export type DashboardSyncStatus =
  | "missing_table"
  | "no_rows"
  | "success"
  | "failed"
  | "dry_run"
  | "unknown";

export interface DashboardSyncMeta {
  table_available: boolean;
  status: DashboardSyncStatus;
  latest_sync_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  postgres_mirror_note: string;
  canonical_contact_count: number;
  canonical_organization_count: number;
  canonical_opportunity_signal_count: number;
  archive_contact_count: number;
  archive_organization_count: number;
  archive_opportunity_signal_count: number;
  email_suppression_count: number;
  domain_suppression_count: number;
  outreach_state_count: number;
  error_message: string | null;
}

export interface ClassificationSummary {
  scope: "canonical";
  table_available: boolean;
  status: "missing_table" | "no_rows" | "ok";
  total_rows: number;
  counts_by_label: Record<string, number>;
  kpi: Record<string, number>;
  disclaimer: string;
}

export interface ClassificationEmailRow {
  email_id: number;
  date_iso: string | null;
  folder: string | null;
  from_addr: string | null;
  to_addrs: string | null;
  subject: string | null;
  predicted_label: string;
  confidence: string;
  ambiguous: boolean;
  recommended_action: string;
  etiqueta_ui: string;
  evidence: string | null;
  contact_email: string | null;
  contact_domain: string | null;
}

export interface ClassificationRecent {
  scope: "canonical";
  table_available: boolean;
  items: ClassificationEmailRow[];
  total: number;
  limit: number;
  label_filter: string | null;
}

export interface ClassificationActionGroup {
  recommended_action: string;
  action_label_es: string;
  count: number;
  sample_subjects: string[];
}

export interface ClassificationActions {
  scope: "canonical";
  table_available: boolean;
  groups: ClassificationActionGroup[];
  disclaimer: string;
}

export interface OutboundReadiness {
  verdict: "ready" | "ready_with_warnings" | "not_ready" | "unknown";
  warnings: string[];
  errors: string[];
  eventually_consistent: boolean;
  disclaimer: string;
  data_source: string;
}
