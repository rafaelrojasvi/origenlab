/** Types for GET /mirror/audits/gmail-interactions (read-only SQLite audit snapshot). */

export interface GmailInteractionAuditDomainRow {
  domain: string;
  message_count: number;
  sent_count: number;
  received_count: number;
  thread_count: number;
  latest_email_at: string | null;
  latest_subject_safe: string;
  has_attachments: boolean;
  matched_aliases: string[];
}

export interface GmailInteractionAuditSnapshot {
  schema_version: number;
  generated_at_utc: string;
  source: string;
  lookback_days: number;
  domains: GmailInteractionAuditDomainRow[];
}

export interface GmailInteractionAuditResponse {
  status: "ok" | "snapshot_missing";
  message: string;
  snapshot: GmailInteractionAuditSnapshot | null;
  updated_at: string | null;
  source: "postgres_snapshot" | "filesystem_active_current" | null;
  snapshot_stale: boolean | null;
  read_only: boolean;
}
