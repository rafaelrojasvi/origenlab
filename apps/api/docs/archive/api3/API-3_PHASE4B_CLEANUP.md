# API-3 Phase 4B — Post-audit cleanup and Phase 6 gate prep

**Status:** Complete (2026-05). Legacy `:8000` **not removed**. Phase 6 grep gate added; **not required to pass** until sign-off.

---

## Deliverables

| Task | Result |
|------|--------|
| `POSTGRES_API_DASHBOARD_PLAN.md` deprecation banner | **Done** — top banner + historical deployment notes |
| Streamlit tests (`:8001` default, `/mirror/*` paths) | **Done** — `tests/test_streamlit_api_preview.py` |
| Parked `src/legacy/README.md` | **Done** — revival must use `:8001` `/mirror/*` |
| Phase 6 grep gate | **`apps/api/scripts/api3_phase6_grep_gate.sh`** + allowlist |
| Policy tests | **`tests/mirror/test_mirror_phase4b_cleanup.py`** |

---

## Phase 6 grep gate

```bash
# Expected to FAIL until legacy tree and deprecated refs are removed (Phase 6)
apps/api/scripts/api3_phase6_grep_gate.sh

# Report only (exit 0)
API3_PHASE6_GATE_WARN_ONLY=1 apps/api/scripts/api3_phase6_grep_gate.sh
```

Allowlist: `apps/api/scripts/api3_phase6_grep_allowlist.txt` (path prefixes).

---

## Related

| Doc | Role |
|-----|------|
| [API-3_PHASE4A_REFERENCE_AUDIT.md](./API-3_PHASE4A_REFERENCE_AUDIT.md) | Phase 4A classification |
| [API-3_PHASE3C_DEPRECATION.md](./API-3_PHASE3C_DEPRECATION.md) | Deprecation headers |
