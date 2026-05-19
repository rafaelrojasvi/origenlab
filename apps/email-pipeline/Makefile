# Email-pipeline operator shortcuts (docs-first; no hidden dependencies).
# Run from apps/email-pipeline/: make doctor

DATE_SUFFIX ?= $(shell date +%Y%m%d)

.PHONY: doctor safety-refresh equipment-queue audit operator-status help

help:
	@echo "Email-pipeline operator shortcuts (from apps/email-pipeline/)"
	@echo ""
	@echo "  make doctor              operator-status + check_reproducibility"
	@echo "  make operator-status     read-only SQLite / manifest / DNR summary"
	@echo "  make audit               operator-status + check_outbound_readiness"
	@echo "  make equipment-queue     build equipment-first opportunity + operator queues"
	@echo "  make equipment-queue DATE_SUFFIX=YYYYMMDD   override date suffix (default: today)"
	@echo "  make safety-refresh      prints ingest + refresh commands only (does not run them)"
	@echo ""
	@echo "DATE_SUFFIX=$(DATE_SUFFIX)"

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
	@cd "$(CURDIR)" && uv run python scripts/qa/build_equipment_first_opportunity_queue.py --date-suffix $(DATE_SUFFIX)
	@cd "$(CURDIR)" && uv run python scripts/qa/build_equipment_first_operator_queue.py --date-suffix $(DATE_SUFFIX)

audit:
	@cd "$(CURDIR)" && uv run python scripts/qa/operator_status.py
	@cd "$(CURDIR)" && uv run python scripts/qa/check_outbound_readiness.py
