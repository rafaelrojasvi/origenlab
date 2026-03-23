# Data Locations (Email Pipeline)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-23

Use environment variables as the source of truth for local data paths (template: [`.env.example`](../.env.example)). Procedures: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path).

<a id="m-epdata-root"></a>
## Default local root

- Linux/WSL default root: `$HOME/data/origenlab-email`
- Common subpaths:
  - `raw_pst/`
  - `mbox/`
  - `sqlite/emails.sqlite`
  - `jsonl/`
  - `reports/`

<a id="m-epdata-windows"></a>
## Windows Explorer access (WSL)

Use:

`\\wsl.localhost\<DistroName>\home\<user>\data\origenlab-email`

Replace `<DistroName>` and `<user>` with your environment values.

<a id="m-epdata-policy"></a>
## Path policy

- Do not hardcode machine-specific absolute paths in runbooks.
- Prefer environment variables and documented defaults.
- Keep sensitive archives and generated outputs outside git.
