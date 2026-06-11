# Security policy

## Public repository notice

OrigenLab is a **public** monorepo. It documents operator workflows but must not contain live credentials, mailbox exports, SQLite files, generated reports, or client operational data.

## Reporting a vulnerability

**Do not** open a public issue with exploit details, secrets, stack traces containing tokens, or live customer/mailbox data.

1. Contact the maintainers through a **private** channel (direct message or email to the project owner).
2. Include: affected component (`apps/web`, `apps/api`, `apps/dashboard`, `apps/email-pipeline`), reproduction steps, and suspected impact.
3. Allow reasonable time for triage before any public disclosure.

## If a secret was exposed

1. **Revoke and rotate immediately** (OAuth tokens, app passwords, API keys, database passwords).
2. Remove the secret from tracked files and Git history if applicable.
3. Notify maintainers privately with what was exposed and what was rotated.

Operational data (CSVs, JSONL, SQLite, PST/mbox) never belongs in Git. If committed, treat as a data exposure: stop publishing, remove from tracking, and assess PII impact.

## Sensitive data handling

- Email archives, database files, JSONL exports, generated client reports, and `.env` files with credentials must **not** be committed.
- The email pipeline may process real mailbox content locally. Treat logs, reports, and database copies as sensitive.
- See [`docs/SECURITY_PUBLIC_REPO.md`](docs/SECURITY_PUBLIC_REPO.md) for the public-repo checklist and [`apps/email-pipeline/docs/SECURITY.md`](apps/email-pipeline/docs/SECURITY.md) for pipeline-specific notes.
