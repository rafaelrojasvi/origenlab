/** Client-side filter for internal OrigenLab mailboxes (no API calls). */

import { emailDomain } from "./clientTableView";

/** Domains treated as internal outbound / historical lab mailboxes. */
export const INTERNAL_OPERATOR_DOMAINS = ["origenlab.cl", "labdelivery.cl"] as const;

export function isInternalOperatorContact(email: string): boolean {
  const trimmed = email.trim().toLowerCase();
  if (!trimmed.includes("@")) {
    return false;
  }
  const domain = emailDomain(trimmed);
  return INTERNAL_OPERATOR_DOMAINS.some((d) => domain === d);
}
