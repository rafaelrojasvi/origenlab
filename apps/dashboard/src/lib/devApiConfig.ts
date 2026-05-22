/**
 * Local dev guardrails for VITE_ORIGENLAB_API_BASE_URL (Dashboard v1 → apps/api :8001).
 */

export const LEGACY_DEV_PORT_WARNING =
  "Dashboard is configured to call :8000 directly. For local Dashboard v1, unset VITE_ORIGENLAB_API_BASE_URL and use the Vite proxy to apps/api on :8001.";

/** True when URL targets legacy email-pipeline port on loopback (dev misconfiguration). */
export function isLegacyDevPortBaseUrl(baseUrl: string | undefined): boolean {
  const raw = baseUrl?.trim();
  if (!raw) {
    return false;
  }
  try {
    const u = new URL(raw.includes("://") ? raw : `http://${raw}`);
    const host = u.hostname.toLowerCase();
    const port = u.port || (u.protocol === "https:" ? "443" : "80");
    return port === "8000" && (host === "127.0.0.1" || host === "localhost");
  } catch {
    return /(?:127\.0\.0\.1|localhost):8000\b/i.test(raw);
  }
}

/** Testable helper: warn in non-production when env points at legacy :8000. */
export function getLegacyDevPortWarningForEnv(
  mode: string,
  apiBaseUrl: string | undefined,
): string | null {
  if (mode === "production") {
    return null;
  }
  if (!isLegacyDevPortBaseUrl(apiBaseUrl)) {
    return null;
  }
  return LEGACY_DEV_PORT_WARNING;
}

export function getLegacyDevPortWarning(): string | null {
  return getLegacyDevPortWarningForEnv(
    import.meta.env.MODE,
    import.meta.env.VITE_ORIGENLAB_API_BASE_URL,
  );
}

export function logLegacyDevPortWarningIfNeeded(): void {
  const warning = getLegacyDevPortWarning();
  if (warning) {
    console.warn(`[OrigenLab Dashboard] ${warning}`);
  }
}
