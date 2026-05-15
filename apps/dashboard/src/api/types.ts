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

export interface OutboundReadiness {
  verdict: "ready" | "ready_with_warnings" | "not_ready" | "unknown";
  warnings: string[];
  errors: string[];
  eventually_consistent: boolean;
  disclaimer: string;
  data_source: string;
}
