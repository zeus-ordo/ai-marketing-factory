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
