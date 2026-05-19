# Email-pipeline operator shortcuts (docs-first; no hidden dependencies).
# Run from apps/email-pipeline/: make doctor

.PHONY: doctor safety-refresh equipment-queue audit operator-status help

help:
	@echo "Targets: doctor | operator-status | safety-refresh | equipment-queue | audit"

doctor: operator-status
	@cd "$(CURDIR)" && uv run python scripts/qa/check_reproducibility.py

operator-status:
	@cd "$(CURDIR)" && uv run python scripts/qa/operator_status.py

safety-refresh:
	@echo "Read-only status first; run ingest + refresh only with explicit approval."
	@cd "$(CURDIR)" && uv run python scripts/qa/operator_status.py
	@echo "--- To refresh (mutates SQLite via ingest + exports): ---"
	@echo "  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder \"[Gmail]/Enviados\""
	@echo "  uv run python scripts/qa/refresh_outbound_safety_memory.py"

equipment-queue:
	@cd "$(CURDIR)" && uv run python scripts/qa/build_equipment_first_opportunity_queue.py --date-suffix 20260518
	@cd "$(CURDIR)" && uv run python scripts/qa/build_equipment_first_operator_queue.py --date-suffix 20260518

audit:
	@cd "$(CURDIR)" && uv run python scripts/qa/operator_status.py
	@cd "$(CURDIR)" && uv run python scripts/qa/check_outbound_readiness.py
