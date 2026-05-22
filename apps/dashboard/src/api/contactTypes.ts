/** Types for GET /contacts/{email} (read-only contact intelligence). */

export type ContactDataSource = "sqlite" | "postgres_mirror";

export interface ContactMeta {
  data_source: ContactDataSource;
  read_only: boolean;
  reduced_mode: boolean;
  note: string;
}

export interface ContactProfileFields {
  email: string;
  normalized_email: string;
  name: string;
  domain: string;
  organization_name: string;
  organization_domain: string;
  last_seen_at: string | null;
  first_seen_at: string | null;
  message_count: number;
}

export interface ContactOutreachFields {
  state: string | null;
  last_contacted_at: string | null;
  source: string | null;
  notes: string | null;
  do_not_repeat: boolean;
  suppressed_email: boolean;
  suppressed_domain: boolean;
}

export interface ContactSentHistoryFields {
  sent_count: number;
  latest_sent_at: string | null;
  latest_subject: string | null;
}

export interface ContactProfileUi {
  meta: ContactMeta;
  contact: ContactProfileFields;
  outreach: ContactOutreachFields;
  sent_history: ContactSentHistoryFields;
  warnings: string[];
}
