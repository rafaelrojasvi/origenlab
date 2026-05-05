# Public Release Checklist

Use this checklist before changing repository visibility from private to public.

## 1) Secrets and credentials

- [ ] No `.env` files are tracked
- [ ] No API keys, OAuth client secrets, access tokens, app passwords, or private keys are tracked
- [ ] No hardcoded credentials remain in scripts, tests, docs, or examples
- [ ] If any secret was ever committed, history is rewritten and the secret is rotated

## 2) Operational and client data

- [ ] No real PST/mbox/sqlite/jsonl artifacts are tracked
- [ ] No generated report outputs with real names/emails are tracked
- [ ] No lead export CSVs or client pack snapshots with sensitive details are tracked
- [ ] `reports/out/` tracking is limited to intentional placeholders (`README.md`, `.gitkeep`)

## 3) Documentation safety

- [ ] README and docs avoid disclosing private infrastructure details
- [ ] Portfolio screenshots redact personal data, inbox addresses, or client identifiers when needed
- [ ] Claims in docs are truthful and consistent with business rules

## 4) Legal and licensing

- [ ] You have rights to publish included assets (images, logos, third-party materials)
- [ ] License file is present and accurate
- [ ] Any third-party attribution requirements are satisfied

## 5) Repository hygiene

- [ ] `.gitignore` protects secrets and generated artifacts
- [ ] Build/test commands run successfully on a fresh clone
- [ ] Root README clearly explains scope and limitations
- [ ] SECURITY and CONTRIBUTING docs are present and current

## 6) Final verification commands

Run from repository root:

```bash
git ls-files | rg "\.env$|\.sqlite$|\.jsonl$|\.pst$|\.mbox$"
git ls-files | rg "reports/out"
git status --short
```

If these checks look clean and your manual review passes, the repository is ready for public visibility.
