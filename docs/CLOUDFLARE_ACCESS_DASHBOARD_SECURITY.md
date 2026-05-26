# Cloudflare Access — dashboard and API protection

Runbook and **production record** for protecting **dashboard.origenlab.cl** and **api.origenlab.cl** with Cloudflare Zero Trust (Access).

**Status (2026-05-26):** Access is **enabled in production**. Operators must authenticate before reaching the dashboard or API on the custom domains.

## Production result (2026-05-26)

### Cloudflare zone

| Item | Value |
|------|--------|
| Zone | **origenlab.cl** — **Active** |
| Nameservers | `damiete.ns.cloudflare.com` |
| | `robin.ns.cloudflare.com` |

### Protected Access applications

| Application | Hostname |
|-------------|----------|
| Dashboard | `dashboard.origenlab.cl` |
| API | `api.origenlab.cl` |

### Access policy

| Field | Value |
|-------|--------|
| Policy name | **Allow OrigenLab admins** |
| Action | Allow |
| Include | Email |
| Allowed emails | `rafarojasv6@gmail.com` |
| | `tvivancob@gmail.com` |

### Application configuration (verified)

| Component | Setting |
|-----------|---------|
| Dashboard API base | `VITE_ORIGENLAB_API_BASE_URL=https://api.origenlab.cl` |
| API CORS | `ORIGENLAB_API_CORS_ORIGINS` includes `https://dashboard.origenlab.cl` |

### Verification (production)

| Check | Result |
|-------|--------|
| `https://dashboard.origenlab.cl` in browser (incognito) | Cloudflare Access login / code flow appears |
| `https://api.origenlab.cl` in browser (incognito) | Cloudflare Access login / code flow appears |
| `curl -i https://api.origenlab.cl/health` | **HTTP/2 302** redirect to Cloudflare Access login (not anonymous 200) |

### Note: `HEAD /health` and 405

After authenticating through Access, `HEAD /health` may return **405 Method Not Allowed** because the API only allows **GET** on `/health`. This is expected and **not** an Access misconfiguration. Use **GET** for health checks through Access.

```bash
# Example (after Access session cookie or service token):
curl -i -X GET https://api.origenlab.cl/health
```

## Remaining hardening (follow-up)

Cloudflare Access protects **custom domains** on the zone. **Raw Render URLs may still bypass Access** unless separately restricted.

| URL | Risk | Action |
|-----|------|--------|
| `https://origenlab.onrender.com` | API may be reachable without Access | Test in incognito; if public, mitigate |
| `https://origenlab-dashboard.onrender.com` | Dashboard may be reachable without Access | Test in incognito; if public, mitigate |

**Mitigation options (if raw URLs are still public):**

1. Render **custom domain** settings — prefer `*.origenlab.cl` only; disable or avoid publishing default `*.onrender.com` hostnames where Render allows.
2. **API host allowlist** — e.g. `ORIGENLAB_ALLOWED_HOSTS=api.origenlab.cl` (rejects wrong `Host`; does not block direct Render hostname unless combined with other controls).
3. **Cloudflare Access JWT validation** at the API — validate `CF-Access-JWT-Assertion` on origin for defense in depth.
4. Do not bookmark or document raw Render URLs for operators.

**Test command (unauthenticated):**

```bash
curl -i https://origenlab.onrender.com/health
curl -i https://origenlab-dashboard.onrender.com/
```

Document outcome in this file when tested.

## Goals

- Require identity (Google via Access) for operator access to the commercial dashboard and API.
- Allow only approved operator emails; deny everyone else by default.
- Avoid leaving the API reachable on the public internet while only the dashboard is protected.

## Preconditions (completed for production)

| Check | Status |
|--------|--------|
| `dashboard.origenlab.cl` DNS → Render **origenlab-dashboard** | Done |
| `api.origenlab.cl` DNS → Render **origenlab-api** | Done |
| API **CORS** allows `https://dashboard.origenlab.cl` | Done |
| Access apps on dashboard + API hostnames | Done |
| Operator emails in Allow policy | Done |

### CORS reminder

The dashboard calls `https://api.origenlab.cl` after Access login. Production must keep `ORIGENLAB_API_CORS_ORIGINS` including `https://dashboard.origenlab.cl` (not `*`).

## Cloudflare Access setup (reference)

1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Access** → **Applications**.
2. **Application type:** Self-hosted.
3. Two applications (production):
   - `dashboard.origenlab.cl`
   - `api.origenlab.cl`
4. **Session duration:** 12h or 24h (operator preference).
5. **Identity provider:** Google.
6. **Policy — Allow OrigenLab admins:** Include emails listed above; no catch-all Allow.

### Protect both dashboard and API

If only **dashboard.origenlab.cl** is behind Access, **api.origenlab.cl** (and any raw Render API URL) may remain directly callable. Production protects **both** hostnames.

## Verification checklist (ongoing)

| Step | Expected |
|------|----------|
| Open `https://dashboard.origenlab.cl` in incognito | Redirect to Cloudflare Access / login |
| Log in with **allowed** email | Dashboard loads; API calls succeed (no CORS errors) |
| Log in with **disallowed** email | Blocked by Access |
| `curl -i https://api.origenlab.cl/health` (no session) | **302** to Access login |
| Dashboard → network tab after login | Requests to `api.origenlab.cl` succeed |
| `GET /health` after login | **200** (not HEAD unless API adds HEAD) |
| Raw Render URLs | Confirm blocked or mitigated (see **Remaining hardening**) |

## Rollback

1. Zero Trust → Access → Application → **Disable** or relax the Allow policy temporarily.
2. Leave Render services and Postgres **unchanged** (no redeploy required for Access-only rollback).
3. Do **not** modify SQLite or Postgres for Access rollback.
4. Re-enable policy after operators confirm login flow.

## Deployment interaction

| Change type | Action |
|-------------|--------|
| Cloudflare Access policies / DNS on zone | Cloudflare UI only |
| API CORS env | Redeploy **origenlab-api** on Render |
| Dashboard `VITE_ORIGENLAB_API_BASE_URL` | Redeploy **origenlab-dashboard** |
| Postgres mirror | **Not** required for Access |

**Access itself does not require** a Render redeploy, DB changes, sends, or Postgres sync.

## Safety

- Enabling or changing Access policies does **not** mutate Gmail, SQLite operational data, outreach tables, or Postgres mirror content.
- No mart rebuild required for Access verification.
- Commercial deal ledger and email-pipeline operator writes remain independent of this layer.

## Related docs

- [`SECURITY_AUDIT_RENDER_DASHBOARD.md`](SECURITY_AUDIT_RENDER_DASHBOARD.md) — Render exposure audit and hardening backlog
- [`apps/email-pipeline/docs/REFRESH_RENDER_DASHBOARD_ONCE.md`](../apps/email-pipeline/docs/REFRESH_RENDER_DASHBOARD_ONCE.md) — mirror refresh after data fixes
- [`apps/email-pipeline/docs/PHASE1_CLOUD_READ_PATH.md`](../apps/email-pipeline/docs/PHASE1_CLOUD_READ_PATH.md) — cloud read path and URLs
