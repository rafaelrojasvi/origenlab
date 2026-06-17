import type { OperatorPathInfoMap, RedactedPathInfo } from "../api/operatorTypes";

/** Human-readable label for API redacted path companions (basename + kind only). */
export function formatRedactedPathLabel(info: RedactedPathInfo): string {
  const kind = info.kind?.trim() || "path";
  if (info.redacted) {
    return `${info.basename} (${kind}, redacted)`;
  }
  return `${info.basename} (${kind})`;
}

/** Prefer redacted path info; fall back to legacy raw path string when absent. */
export function formatOperatorPathDisplay(
  raw: string | null | undefined,
  info?: RedactedPathInfo | null,
): string | null {
  if (info?.basename) {
    return formatRedactedPathLabel(info);
  }
  const trimmed = raw?.trim();
  return trimmed || null;
}

/** Resolve a nested section path field via section.path_info when present. */
export function formatSectionPathDisplay(
  key: string,
  raw: string | null | undefined,
  pathInfo?: OperatorPathInfoMap | null,
): string | null {
  return formatOperatorPathDisplay(raw, pathInfo?.[key]);
}
