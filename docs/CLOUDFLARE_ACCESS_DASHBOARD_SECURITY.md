# Cloudflare Access — dashboard and API protection

Runbook for protecting **dashboard.origenlab.cl** and **api.origenlab.cl** with Cloudflare Zero Trust (Access). **Preparation only** — do not apply DNS, Access policies, or Render changes until explicitly approved.

## Goals

- Require Google identity for operator access to the commercial dashboard and API.
- Allow only approved operator emails; deny everyone else by default.
- Avoid leaving the API reachable on the public internet while only the dashboard is protected.

## Preconditions (verify before enabling Access)

| Check | Why it matters |
|--------|----------------|
| `dashboard.origenlab.cl` DNS exists and points to the Render **origenlab-dashboard** service | Access sits in front of the hostname users will use |
| `api.origenlab.cl` DNS exists and points to the Render **origenlab-api** service | Dashboard fetches warm cases and health from this host |
| API **CORS** allows `https://dashboard.origenlab.cl` (and does not rely on `*` in production) | Browser calls after Access login must not fail CORS |
| Render **onrender.com** raw URLs are not shared publicly (bookmarks, docs, integrations) | Access protects custom domains, not necessarily `*.onrender.com` |
| Operator Google accounts exist for Rafael, Tatiana, and any backup admin | IdP allowlist must match real logins |

### CORS reminder

After Access is enabled, the dashboard still calls `https://api.origenlab.cl`. Confirm `ORIGENLAB_CORS_ORIGINS` (or equivalent) on the API service includes `https://dashboard.origenlab.cl`.

### Raw Render URL exposure

Cloudflare Access applies to hostnames configured on the Access application. Traffic to `https://origenlab.onrender.com` (or similar) may bypass Access unless separately restricted. Treat raw URLs as **out of scope** for this runbook’s first cut; plan a follow-up:

- Do not publish raw API/dashboard URLs in runbooks or client-facing docs.
- Optional later: API middleware validating `CF-Access-JWT-Assertion` or an origin/shared-secret guard for non-Access traffic.
- Optional later: Render IP allowlist or private networking if Cloudflare Tunnel is adopted.

## Cloudflare Access setup (manual)

1. Log in to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Access** → **Applications** → **Add an application**.
2. **Application type:** Self-hosted.
3. Create applications (choose one pattern):
   - **Recommended:** two applications  
     - App 1: `dashboard.origenlab.cl`  
     - App 2: `api.origenlab.cl`
   - **Alternative:** one application with both hostnames in **Application domain** (only if session/cookie behavior is verified for cross-origin API calls from the dashboard).
4. **Session duration:** 12h or 24h (operator preference).
5. **Identity provider:** Google (Workspace or Google as OIDC).
6. **Policy — Allow** (example):
   - Action: Allow
   - Include: Emails — `rafael@…`, `tatiana@…`, optional backup admin
   - Require: nothing extra for phase 1, or MFA if available
7. **Policy — implicit deny:** No catch-all Allow; unlisted users must not reach the origin.

### Protect both dashboard and API

If only **dashboard.origenlab.cl** is behind Access, **api.origenlab.cl** (and any raw Render API URL) remains directly callable. Always protect the API hostname used by the dashboard in production.

## Verification checklist (after enable — incognito)

| Step | Expected |
|------|----------|
| Open `https://dashboard.origenlab.cl` in incognito | Redirect to Cloudflare Access / Google login |
| Log in with **allowed** email | Dashboard loads; warm cases and equipment load without CORS errors |
| Log in with **disallowed** email | Blocked by Access (no dashboard) |
| Open `https://api.origenlab.cl/health` in incognito | Protected per policy (login required or 403), not anonymous open API unless intentionally public |
| Dashboard → network tab after login | API requests to `api.origenlab.cl` succeed |
| Existing automation (`curl`, CI) | Only works through intended path (Access service token, VPN, or temporary policy exception) — document any exception |

## Rollback

1. Zero Trust → Access → Application → **Disable** or relax the Allow policy temporarily.
2. Leave Render services and Postgres **unchanged** (no redeploy required for rollback).
3. Do **not** modify the database for Access rollback.
4. Re-enable stricter policy once operators confirm login flow.

## Deployment interaction

| Change type | Action |
|-------------|--------|
| API normalization / CORS only | Redeploy **origenlab-api** on Render |
| Dashboard presets / fetch only | Redeploy **origenlab-dashboard** |
| Cloudflare Access policies | Cloudflare UI only (this doc) |
| Postgres mirror | **Not** required for Access or read-path normalization |

## Safety

- This document does **not** enable Access, change DNS, or change Render env vars.
- No Gmail sends, mirror rebuild, or destructive SQL tied to Access prep.
- Approve hostname, allowlist emails, and session length with operators before step 1 in **Cloudflare Access setup**.

## Related docs

- `apps/email-pipeline/docs/REFRESH_RENDER_DASHBOARD_ONCE.md` — mirror refresh after data fixes
- `apps/email-pipeline/docs/PHASE1_CLOUD_READ_PATH.md` — cloud read path and URLs
