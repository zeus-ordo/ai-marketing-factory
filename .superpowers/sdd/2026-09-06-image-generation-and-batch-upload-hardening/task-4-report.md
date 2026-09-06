# Task 4 Report

## Changed Files

- `app/campaigns/page.tsx`
- `lib/api/campaigns.ts`
- `lib/i18n/translations.ts`
- `scripts/test-batch-upload-contract.mjs`
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-4-report.md`

The pre-existing change in `services/campaign_service/app/persistence.py` was not modified.

## Red/Green Evidence

- RED command: `node scripts/test-batch-upload-contract.mjs`
- RED result: failed as expected with `Error: typed per-file upload states are required` before production changes.
- GREEN command: `node scripts/test-batch-upload-contract.mjs`
- GREEN result: `batch upload contract test passed (14 assertions)`.

## Verification

- `node scripts/test-batch-upload-contract.mjs`: PASS, 14 assertions.
- `npm run lint`: PASS, 0 errors and 11 existing warnings.
- `npm run build`: PASS, production build and TypeScript completed. Next.js reported the existing multiple-lockfile workspace-root warning.
- `git diff --check`: PASS.

## Re-review Fixes

- Added `GET /api/v1/campaigns/upload-policy`, returning the campaign service's configured size, extensions, and MIME map. The client fetches this policy before preflight; the documented fallback is used only by the standalone helper when no policy is supplied.
- Added executable configured-limit boundary coverage: exactly-at-limit is accepted and one byte over is rejected.
- Added executable campaign-start coverage: only all-success selected states enable start; uploading and failed states remain disabled.
- Preserved bounded concurrency, nested failure propagation, immediate state callbacks, knowledge retry/removal, localized stable error codes, and reference/folder IDs.

## Re-review Verification

- RED command: `node scripts/test-batch-upload-contract.mjs`
- RED result: failed as expected with `configured-size boundary contract failed` before policy-object support and start-gate implementation.
- GREEN command: `node scripts/test-batch-upload-contract.mjs`
- GREEN result: `batch upload contract test passed (14 assertions)` and `executable helper assertions passed (5 scenarios)`.
- `npm run lint`: PASS, 0 errors and 11 existing warnings.
- `npm run build`: PASS, TypeScript and production build completed; existing multiple-lockfile workspace-root warning remains.
- `python -m pytest services/campaign_service/test_batch_upload.py -q`: PASS, 12 passed, 2 existing deprecation warnings.

## Re-review Concerns

- The standalone helper fallback remains 50 MiB for non-HTTP/test callers; the campaign page does not use it silently because policy fetch failure blocks preflight with a localized error.
- Existing lint warnings, FastAPI deprecation warnings, and the Next.js multiple-lockfile warning remain.

## Final Re-review Fixes

- Removed the runtime frontend environment and hardcoded 50 MiB fallback from the page/helper preflight path. The page fetches the backend upload policy before preflight; policy failure is localized and blocks the flow. `preflightCampaignReferenceFiles` now requires an explicit policy object.
- Added executable policy-path coverage using a backend-shaped policy: exact limit is accepted, over-limit is rejected before upload, and the page fetch/use path is asserted.
- Added executable start-gate coverage for all-success, uploading, and failed states.
- Added `mergeBatchUploadStates` and used functional state updates for initial and retry callbacks so successful entries and IDs remain present during failed-file retries.
- Added UTF-8 assertions for Traditional Chinese and Japanese strings and verified the page selects the localized keys.

## Final Re-review Verification

- RED command: `node scripts/test-batch-upload-contract.mjs`
- RED result: failed as expected with `retry updates must merge into the complete state` before the merge helper was implemented.
- GREEN command: `node scripts/test-batch-upload-contract.mjs`
- GREEN result: `batch upload contract test passed (19 assertions)` and `executable helper assertions passed (6 scenarios)`.
- `npm run lint`: PASS, 0 errors and 11 existing warnings.
- `npm run build`: PASS, TypeScript and production build completed; existing multiple-lockfile workspace-root warning remains.
- `python -m pytest services/campaign_service/test_batch_upload.py -q`: PASS, 12 passed, 2 existing deprecation warnings.
- `git diff --check`: PASS.

## Final Concerns

- The page intentionally blocks if `/api/v1/campaigns/upload-policy` is unavailable; no production fallback can silently diverge from backend policy.
- Existing lint, FastAPI deprecation, and Next.js workspace-root warnings remain.

## Implementation

- Added typed `pending | uploading | success | failed` file state.
- Added client size, extension, and MIME preflight using the backend's 50 MiB and allowed-type contract.
- Added a bounded three-worker upload queue and inspected `Promise.allSettled` outcomes.
- Blocked campaign start on failed or incomplete files.
- Added retry-only-failed and remove actions while preserving successful reference and folder IDs.
- Added English, Traditional Chinese, and Japanese upload-state and campaign-start-blocked strings.

## Concerns

- Lint retains 11 pre-existing warnings in campaign/system/review files.
- Build retains the existing multiple-lockfile workspace-root warning.
- Knowledge-library attachment failures were initially surfaced by the gate but lacked retry support; this was resolved below with the review fixes.

## Review Fixes

- Added `lib/api/batch-upload.ts` as the executable, shared batch state machine.
- Office `.doc`, `.docx`, `.ppt`, and `.pptx` files now accept the backend-approved `application/octet-stream`; unsafe MIME mismatches remain rejected.
- Worker-level `Promise.allSettled` results are inspected per upload, with stable `errorCode` values propagated through state callbacks.
- State callbacks run on each `uploading`, `success`, and `failed` transition, so active progress renders immediately.
- Knowledge attachments use the same bounded retryable state flow; failed entries can be retried or removed, and removal recomputes the start gate.
- UI error rendering now localizes stable codes and does not display raw API exception text.
- Client size configuration is exposed as `NEXT_PUBLIC_REFERENCE_MAX_SIZE_BYTES`, with the backend-compatible 50 MiB fallback; deployments should set it to the same value as `REFERENCE_MAX_SIZE_BYTES`.
- The contract test now transpiles and executes the helper with assertions for MIME compatibility, concurrency, transitions, nested failures, ID preservation, retry filtering, and localized/removal behavior.

## Follow-up Verification

- RED command: `node scripts/test-batch-upload-contract.mjs`
- RED result: failed as expected with `ENOENT` for the not-yet-created `lib/api/batch-upload.ts` helper after the existing 14 source assertions passed.
- GREEN command: `node scripts/test-batch-upload-contract.mjs`
- GREEN result: `batch upload contract test passed (14 assertions)` and `executable helper assertions passed (3 scenarios)`.
- `npm run lint`: PASS, 0 errors and 11 existing warnings.
- `npm run build`: PASS, TypeScript and production build completed; existing multiple-lockfile workspace-root warning remains.
- `python -m pytest services/campaign_service/test_batch_upload.py -q`: PASS, 12 passed, 2 existing deprecation warnings.
- `git diff --check`: PASS.
