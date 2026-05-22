/** Safe string helpers for API → UI normalization (no paths or bodies). */

export function safeStr(value: unknown): string {
  if (value == null) {
    return "";
  }
  return String(value);
}

/** Strip path-like fragments from preview text shown in tables. */
export function safePreviewText(value: unknown, maxLen = 500): string {
  let text = safeStr(value).trim();
  if (!text) {
    return "";
  }
  text = text.replace(/(?:\/[\w.-]+)+\.(?:csv|sqlite|db|json|md)\b/gi, "[path redacted]");
  if (text.length > maxLen) {
    return `${text.slice(0, maxLen)}…`;
  }
  return text;
}

export function truncate(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) {
    return t;
  }
  return `${t.slice(0, max)}…`;
}
