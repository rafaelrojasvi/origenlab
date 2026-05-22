# PARKED — legacy dashboard (pre–Dashboard v1)

**Not mounted.** `App.tsx` renders `TodayPage` only, which uses `src/api/operatorClient.ts` against **`apps/api`** on port 8001.

This folder preserves the old multi-tab panel that called **email-pipeline** FastAPI routes (`/dashboard/summary`, `/classification/*`, `/commercial/*`, …) via `legacy/api/client.ts`.

## Do not import from mounted runtime

Active code lives under:

- `src/pages/TodayPage.tsx`
- `src/api/operatorClient.ts`, `operatorTypes.ts`, `commercialTypes.ts`, `commercialParse.ts`
- `src/components/commercial/`, `src/components/operator/`

## Restoration

To revive a legacy tab, copy the relevant module back into `src/` and wire it explicitly in `App.tsx` (not recommended without a product review). Prefer extending Dashboard v1 tables in `apps/api` instead.

## Tests

Legacy unit tests are **excluded** from `npm test` (see `vite.config.ts`). They remain in this tree for reference only.
