# Copy-Length Failure-State Fix

## Status

Implemented and committed as `fix: propagate terminal worker failures`.

## Changes

- Added `invalid_copy_length` classification in orchestrator and campaign-service for `invalid copy body length` and `body length must be between` messages.
- Kept this classification out of retryable error sets.
- Added terminal orchestrator reporting through the existing campaign-service worker-result path with task, campaign, run, sanitized error, classification, and available provider/model data. Reporting remains non-blocking and logs failures through the existing helper.
- Preserved explicit worker errors when campaign-service converts a result with no displayable assets into a failed result.
- Finalized campaign workflow immediately after a failed worker result is applied, so the campaign status becomes `failed` without waiting for reconciliation.
- Added TDD regression coverage for classification, terminal reporting, and immediate campaign failure.

## Tests

- Focused orchestrator regressions: `2 passed`.
- Focused campaign-service regressions: `3 passed`.
- Full orchestrator suite: `32 passed`.
- Full campaign-service suite from repository root: `283 passed, 5 skipped, 1 failed`.
- The one full-suite failure is an existing order-dependent/auth-fixture failure in `test_context_assembler.py::test_asset_regeneration_sends_complete_v2_image_payload_and_sanitizes_audit`; the test passes in isolation (`1 passed`).
- Running the campaign-service suite from its service directory also has an existing collection-path failure because `services` is not importable from that working directory.

## Concerns

- Full campaign-service suite is not clean due to the unrelated order-dependent failure above. No frontend files were changed.
