# Advanced lead scripts

Python entrypoints in this folder are **supporting or exploratory** tooling: contact-hunt merge/import, lead-account rollup and matching, optional `contact_master` exports, archive audit wrappers, and deeper QA.

They are **not** part of the default operator-facing outbound surface. For canonical commands, see [`docs/OUTBOUND_SOURCE_OF_TRUTH.md`](../../../docs/OUTBOUND_SOURCE_OF_TRUTH.md), [`docs/RUNBOOK.md`](../../../docs/RUNBOOK.md), and the root listing in [`../README.md`](../README.md).

Shorter paths may still exist at `scripts/*.py` for some of these (thin wrappers); regression coverage includes the implementation paths under `scripts/leads/advanced/`.
