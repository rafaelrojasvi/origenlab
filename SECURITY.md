# Security policy

## Reporting a vulnerability

If you believe you have found a security vulnerability, **do not** open a public issue with exploit details, stack traces that include secrets, or live customer data.

1. Contact the maintainers through a **private** channel (for example: direct message or email to the project owner).
2. Include: affected component (`apps/web` vs `apps/email-pipeline`), reproduction steps, and suspected impact.
3. Allow reasonable time for triage before any public disclosure.

## Sensitive data in this repository

This monorepo is designed so that **operational and sensitive artifacts stay out of Git**:

- Email archives (for example PST/mbox), database files, JSONL exports, generated client reports, and environment files with credentials must **not** be committed.
- The email pipeline may process real mailbox content locally. Treat any copy/paste from logs, reports, or databases as potentially sensitive.

For additional handling notes specific to the email pipeline, see [`apps/email-pipeline/docs/SECURITY.md`](apps/email-pipeline/docs/SECURITY.md).

## Secrets

Never commit API keys, passwords, OAuth tokens, or private paths to customer data. If a secret was ever exposed in Git history, rotate it immediately and follow your provider’s guidance.
