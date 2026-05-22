/**
 * Defensive parser for GET /contacts/{email}.
 * Strips path-like fragments; never surfaces raw bodies or filesystem hints.
 */

import type {
  ContactMeta,
  ContactOutreachFields,
  ContactProfileFields,
  ContactProfileUi,
  ContactSentHistoryFields,
} from "./contactTypes";
import { safePreviewText, safeStr } from "../lib/safeText";

const FORBIDDEN_KEYS = new Set([
  "body",
  "body_preview",
  "email_body",
  "source_path",
  "sqlite_path",
  "gmail_url",
  "source_file",
]);

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function safeOptionalStr(value: unknown, maxLen: number): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const s = safePreviewText(value, maxLen);
  return s || null;
}

function parseMeta(raw: unknown): ContactMeta {
  const m = asRecord(raw);
  const dataSource = safeStr(m.data_source);
  return {
    data_source: dataSource === "postgres_mirror" ? "postgres_mirror" : "sqlite",
    read_only: m.read_only !== false,
    reduced_mode: Boolean(m.reduced_mode),
    note: safePreviewText(m.note, 500),
  };
}

function parseContact(raw: unknown): ContactProfileFields {
  const c = asRecord(raw);
  return {
    email: safePreviewText(c.email, 200),
    normalized_email: safePreviewText(c.normalized_email, 200),
    name: safePreviewText(c.name, 200),
    domain: safePreviewText(c.domain, 120),
    organization_name: safePreviewText(c.organization_name, 200),
    organization_domain: safePreviewText(c.organization_domain, 120),
    last_seen_at: safeOptionalStr(c.last_seen_at, 80),
    first_seen_at: safeOptionalStr(c.first_seen_at, 80),
    message_count:
      typeof c.message_count === "number" && Number.isFinite(c.message_count)
        ? Math.max(0, Math.floor(c.message_count))
        : 0,
  };
}

function parseOutreach(raw: unknown): ContactOutreachFields {
  const o = asRecord(raw);
  return {
    state: safeOptionalStr(o.state, 80),
    last_contacted_at: safeOptionalStr(o.last_contacted_at, 80),
    source: safeOptionalStr(o.source, 120),
    notes: safeOptionalStr(o.notes, 300),
    do_not_repeat: Boolean(o.do_not_repeat),
    suppressed_email: Boolean(o.suppressed_email),
    suppressed_domain: Boolean(o.suppressed_domain),
  };
}

function parseSentHistory(raw: unknown): ContactSentHistoryFields {
  const s = asRecord(raw);
  return {
    sent_count:
      typeof s.sent_count === "number" && Number.isFinite(s.sent_count)
        ? Math.max(0, Math.floor(s.sent_count))
        : 0,
    latest_sent_at: safeOptionalStr(s.latest_sent_at, 80),
    latest_subject: safeOptionalStr(s.latest_subject, 200),
  };
}

function parseWarnings(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((w) => safePreviewText(w, 400))
    .filter((w) => w.length > 0);
}

/** Reject payloads that include forbidden top-level keys (defense in depth). */
export function assertNoForbiddenContactKeys(data: unknown): void {
  const row = asRecord(data);
  for (const key of Object.keys(row)) {
    if (FORBIDDEN_KEYS.has(key)) {
      throw new Error(`contact response contains forbidden field: ${key}`);
    }
  }
}

export function parseContactDetailResponse(data: unknown): ContactProfileUi {
  assertNoForbiddenContactKeys(data);
  const row = asRecord(data);
  return {
    meta: parseMeta(row.meta),
    contact: parseContact(row.contact),
    outreach: parseOutreach(row.outreach),
    sent_history: parseSentHistory(row.sent_history),
    warnings: parseWarnings(row.warnings),
  };
}
