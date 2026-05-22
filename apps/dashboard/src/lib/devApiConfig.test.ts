import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LEGACY_DEV_PORT_WARNING,
  getLegacyDevPortWarning,
  getLegacyDevPortWarningForEnv,
  isLegacyDevPortBaseUrl,
  logLegacyDevPortWarningIfNeeded,
} from "./devApiConfig";

describe("devApiConfig", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("detects legacy loopback :8000 URLs", () => {
    expect(isLegacyDevPortBaseUrl("http://127.0.0.1:8000")).toBe(true);
    expect(isLegacyDevPortBaseUrl("http://localhost:8000/")).toBe(true);
    expect(isLegacyDevPortBaseUrl("http://127.0.0.1:8001")).toBe(false);
    expect(isLegacyDevPortBaseUrl("https://api.example.com")).toBe(false);
    expect(isLegacyDevPortBaseUrl("")).toBe(false);
  });

  it("returns warning in development when env uses :8000", () => {
    expect(
      getLegacyDevPortWarningForEnv("development", "http://127.0.0.1:8000"),
    ).toBe(LEGACY_DEV_PORT_WARNING);
  });

  it("does not warn in production even for :8000 URL", () => {
    expect(
      getLegacyDevPortWarningForEnv("production", "http://127.0.0.1:8000"),
    ).toBeNull();
  });

  it("does not warn when dev env is unset (Vite proxy)", () => {
    expect(getLegacyDevPortWarningForEnv("development", "")).toBeNull();
    expect(getLegacyDevPortWarningForEnv("development", undefined)).toBeNull();
  });

  it("getLegacyDevPortWarning reads import.meta.env", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://localhost:8000");
    expect(getLegacyDevPortWarning()).toBe(LEGACY_DEV_PORT_WARNING);
  });

  it("logLegacyDevPortWarningIfNeeded warns to console in dev with :8000", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    logLegacyDevPortWarningIfNeeded();
    expect(warn).toHaveBeenCalledWith(`[OrigenLab Dashboard] ${LEGACY_DEV_PORT_WARNING}`);
    warn.mockRestore();
  });

  it("logLegacyDevPortWarningIfNeeded is silent when env unset", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    logLegacyDevPortWarningIfNeeded();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
