#!/usr/bin/env node
/**
 * GET smoke for apps/api Postgres mirror routes (:8001 /mirror/*).
 * API-3 Phase 3A — preferred over smoke:legacy for mirror reporting checks.
 *
 * Requires uvicorn on :8001 with ORIGENLAB_POSTGRES_URL (disposable Postgres).
 * Does not call operator Today routes or legacy :8000 paths.
 */
const base = (
  process.env.ORIGENLAB_MIRROR_API_BASE_URL ||
  process.env.ORIGENLAB_API_MIRROR_BASE_URL ||
  "http://127.0.0.1:8001"
).replace(/\/$/, "");

const routes = [
  ["/mirror/health/dependencies", "dependencies"],
  ["/mirror/dashboard/summary", "summary"],
  ["/mirror/meta/dashboard-sync", "sync"],
  ["/mirror/classification/summary", "classification"],
];

async function get(path) {
  const res = await fetch(`${base}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} → HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

try {
  const results = {};
  for (const [path, key] of routes) {
    results[key] = await get(path);
  }
  console.log("mirror smoke ok:", {
    base,
    dependencies_status: results.dependencies?.status,
    summary_scope: results.summary?.scope,
    contact_count: results.summary?.contact_count,
    sync_status: results.sync?.status,
    classification_status: results.classification?.status,
  });
} catch (err) {
  console.error("mirror smoke failed:", err.message);
  console.error(
    "Hint: cd apps/api && ORIGENLAB_POSTGRES_URL=… uv run uvicorn origenlab_api.main:app --port 8001",
  );
  process.exit(1);
}
