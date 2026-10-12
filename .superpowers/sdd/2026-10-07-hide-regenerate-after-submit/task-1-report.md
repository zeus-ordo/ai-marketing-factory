# Task 1 Report

## Status

Implemented the local submitted-asset tracking behavior in `app/campaigns/page.tsx`.

- Added `regenerateSubmittedAssetIds` as `useState<Set<string>>`.
- Added the regeneration target ID only after `regenerateAsset(...)` resolves.
- Left the catch path unchanged, so failed submissions remain retryable.
- Excluded submitted IDs from the regenerate action condition.
- Preserved the existing modal, validation, payload, loading, refresh, review, and API/data flows.
- Added the focused campaign UI contract assertion.

## TDD Evidence

The focused contract was first run after adding the new assertion and before implementation. It failed with:

`Submitted assets must be excluded from the regenerate action`

After implementation, the new regenerate exclusion assertion passed.

## Verification

- Focused contract: blocked by the pre-existing `Review page must display source provenance` assertion in `scripts/test-campaign-flow-contract.mjs`; the new assertion passes.
- `npx tsc --noEmit`: passed.
- `npm run build`: passed.
- `git diff --check`: passed.
- Isolated regenerate exclusion contract: passed.

## Concerns

The full focused contract was already failing on the unrelated review-page `source_provenance` assertion. No review-page or API/data-contract changes were made because they are outside this task brief.

## Commit

`fix: hide regenerate action after submit`
