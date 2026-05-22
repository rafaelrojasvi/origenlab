# PARKED — legacy dashboard (pre–Dashboard v1)

**Not mounted.** `App.tsx` renders `TodayPage` only, which uses `src/api/operatorClient.ts` against **`apps/api`** on port **8001** (operator routes: `/health`, `/operator/status`, `/cases/warm`, `/contacts/{email}`, …).

This folder preserves the old multi-tab panel. The **email-pipeline `:8000` API was removed in API-3 Phase 6**; `legacy/api/client.ts` now targets **`/mirror/*`** on **:8001** if this UI is ever revived.

## Do not import from mounted runtime

Active code lives under:

- `src/pages/TodayPage.tsx`
- `src/api/operatorClient.ts`, `operatorTypes.ts`, `commercialTypes.ts`, `commercialParse.ts`
- `src/components/commercial/`, `src/components/operator/`

**Active Today must not call `/mirror/*`** — mirror list/reporting routes are for Streamlit, RUNBOOK curls, and `npm run smoke:mirror` only.

## Restoration (if ever needed)

1. Target **`http://127.0.0.1:8001`** (or production `apps/api` URL).
2. Use **`/mirror/*`** paths via `legacy/api/client.ts`.
3. Keep **operator** contact drilldown on **`GET /contacts/{email}`** (not `/mirror/contacts`).

Prefer extending Dashboard v1 tables in `apps/api` instead of remounting this tree.

## References

- [apps/api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md](../../../api/docs/API-3_PHASE6_LEGACY_REMOVAL_COMPLETE.md)
- [apps/api/docs/archive/api3/API-3_PHASE5B_DELETION_PR_PLAN.md](../../../api/docs/archive/api3/API-3_PHASE5B_DELETION_PR_PLAN.md)
