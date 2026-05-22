/** Parse email addresses from operator warning strings (read-only drilldown). */

const EMAIL_IN_TEXT =
  /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

export type WarningSegment =
  | { type: "text"; value: string }
  | { type: "email"; value: string };

export function extractEmailsFromWarning(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const match of text.matchAll(EMAIL_IN_TEXT)) {
    const email = match[0].toLowerCase();
    if (!seen.has(email)) {
      seen.add(email);
      out.push(email);
    }
  }
  return out;
}

/** Split warning into text and email segments for inline contact buttons. */
export function parseWarningSegments(text: string): WarningSegment[] {
  const segments: WarningSegment[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(EMAIL_IN_TEXT)) {
    const start = match.index ?? 0;
    const email = match[0];
    if (start > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, start) });
    }
    segments.push({ type: "email", value: email });
    lastIndex = start + email.length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  if (segments.length === 0) {
    segments.push({ type: "text", value: text });
  }
  return segments;
}
