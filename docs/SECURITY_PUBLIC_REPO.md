# Public repository security

Status: canonical  
Owner: project-maintainers  
Last reviewed: 2026-06-10

This repository is **public**. It contains operator tooling for OrigenLab but must never expose secrets, mailbox exports, SQLite databases, generated reports, credentials, or operational datasets.

## Must never be committed

| Category | Examples |
|----------|----------|
| Secrets / env | `.env`, `.env.local`, OAuth tokens, app passwords, API keys |
| Mail / DB exports | `*.pst`, `*.mbox`, `*.sqlite`, `*.sqlite3`, `*.db`, `*.jsonl` |
| Generated reports | `apps/email-pipeline/reports/out/*` (except `README.md` / `.gitkeep`), `reports/out/*` |
| Pipeline inputs with PII | `apps/email-pipeline/reports/in/*`, `reports/in/*` |
| Client packs | `docs/client/*` |
| Keys / certs | `*.pem`, `*.p12`, `id_rsa` |

Templates such as `.env.example` are allowed; real env files are not.

## Where operational truth lives

| Layer | Location |
|-------|----------|
| SQLite OLTP | Local path outside Git (e.g. `ORIGENLAB_SQLITE_PATH` on operator machine) |
| Gmail | Remote mailbox; ingest runs locally only |
| Postgres / dashboard mirror | Published runtime reporting state — not Git |
| Active workspace | `apps/email-pipeline/reports/out/active/current/` on operator host |

## Safe PR rules

- Commit **code, tests, and docs** only.
- Do not commit generated `reports/out` CSVs, audit logs, or manifest snapshots.
- Redact inbox addresses, client names, and tokens from screenshots and pasted logs before sharing.
- Run `./scripts/security/check-public-repo-hygiene.sh` before opening a PR that touches operator paths.

## Local hygiene command

```bash
./scripts/security/check-public-repo-hygiene.sh
```

Uses `git ls-files` only — no network, no live SQLite/Postgres/Gmail reads.

## GitHub settings checklist

Enable or verify on the repository:

- [ ] Secret scanning (GitHub Advanced Security if available)
- [ ] Push protection for detected secrets
- [ ] Dependabot alerts
- [ ] Dependabot security updates (optional; see `.github/dependabot.yml`)

CI includes `.github/workflows/secret-scan.yml` (gitleaks on push/PR).

## Python / uv dependencies

Dependabot is configured for `pip` on `apps/email-pipeline` and `apps/api`. After merging dependency PRs, run `uv lock` locally in each app and commit lockfile updates when needed.

## If sensitivity grows

Consider making the repository private, splitting public marketing code from operator internals, or moving operational scripts to a private fork.

## Related

- [`SECURITY.md`](../SECURITY.md) — coordinated disclosure
- [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md) — visibility checklist
