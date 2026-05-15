#!/usr/bin/env node
/** Smoke: API health + dashboard summary (canonical default). */
const base = (process.env.VITE_ORIGENLAB_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

async function get(path) {
  const res = await fetch(`${base}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} → HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

try {
  const health = await get("/health");
  const summary = await get("/dashboard/summary");
  console.log("smoke ok:", {
    health: health.status,
    scope: summary.scope,
    contact_count: summary.contact_count,
  });
} catch (err) {
  console.error("smoke failed:", err.message);
  process.exit(1);
}
