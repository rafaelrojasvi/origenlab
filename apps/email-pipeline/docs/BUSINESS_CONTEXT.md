# Email Pipeline Business Context

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-23

<a id="m-epbiz-objective"></a>
## Business objective

Extract high-value commercial signal from historical email archives to support:

- client reporting
- lead/account prioritization
- operational visibility into business communications

<a id="m-epbiz-scope"></a>
## Scope boundaries

- Pipeline outputs are analytical and support-oriented; they are not legal source records.
- Sensitive content must remain outside git-tracked artifacts.
- Historical plans/audits are useful for traceability, not operational truth.

<a id="m-epbiz-reporting"></a>
## Canonical reporting docs

- [`REPORTING.md`](REPORTING.md#m-eprep-mail) (informes correo + paquete leads)
- [`REPORT_SCOPE_CLIENT.md`](REPORT_SCOPE_CLIENT.md)
- [`reporting/OUTPUTS_OVERVIEW.md`](reporting/OUTPUTS_OVERVIEW.md)

<a id="m-epbiz-ml"></a>
## ML and prompts

- [`ml/AI_ML_IMPLEMENTED_SUMMARY.md`](ml/AI_ML_IMPLEMENTED_SUMMARY.md) — qué hay implementado, opciones técnicas, y **prompt LLM** (apéndice).
- Future report derivations (backlog): [`reporting/OUTPUTS_OVERVIEW.md`](reporting/OUTPUTS_OVERVIEW.md)
