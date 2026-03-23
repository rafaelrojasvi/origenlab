# Archive Index

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-23

This folder contains historical, superseded, and snapshot documentation.

## Subsections

- `audits/` - dated architecture and reporting audits
- `plans/` - pre-implementation plans superseded by canonical runbooks/design docs
- `research/` - narrative deep-research, prompt-analysis, and long-form backlog notes (e.g. derived-insights options)
- `snapshots/` - machine-specific or date-specific validation snapshots

## Archive header rules

Each archive file should include:

- `Status: archived`
- `Replaced by: <canonical doc path(s)>`
- `Archived on: YYYY-MM-DD`
- `Why archived: <short reason>`

## What belongs here (policy)

Move or stub toward `ARCHIVE/` when a doc is:

- a **pre-implementation plan** superseded by implemented runbooks or design docs
- a **dated audit** whose operational truth moved to `ARCHITECTURE.md` / `RUNBOOK.md`
- **cohort- or machine-specific** (fixed row counts, local paths, one-off runs)
- **narrative research** not used for day-to-day operations

Top-level `docs/*.md` should prefer **stubs** pointing here so old links keep working.
