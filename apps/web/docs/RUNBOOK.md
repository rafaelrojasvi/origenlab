# Web Runbook

Status: canonical  
Owner: web-maintainers  
Last reviewed: 2026-03-24

<a id="m-webrun-local"></a>
## Local development

```bash
cd apps/web
npm ci   # reproducible install; same as monorepo root quick start (`npm install` also works if you prefer)
npm run dev
```

<a id="m-webrun-validation"></a>
## Validation

```bash
cd apps/web
npm run check
npm run build
```

<a id="m-webrun-deploy"></a>
## Deployment

Use [`deployment.md`](deployment.md) as the canonical operational procedure.

Quick rule:

- Upload the contents of `dist/` (not `dist/` as nested folder) to `public_html`.
- Ensure `.htaccess` is present after upload.

<a id="m-webrun-status"></a>
## Runtime status

Current live-status and DNS notes: [`deployment-status.md`](deployment-status.md).

<a id="m-webrun-mail"></a>
## Mail operations

Mailbox operational source: [`email-setup.md`](email-setup.md).
