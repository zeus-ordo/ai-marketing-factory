# Final Fix Report

Date: 2026-10-20

## Fixes

- `_parse_copy_variant` now rejects an empty body for every body-length contract, including `0-100`; existing title and CTA non-empty/maximum checks are unchanged.
- Both campaign-service regeneration dispatch paths now use `_worker_post_json`, preserving the existing retry, classification, tracing, and backoff behavior. Format mappings and response schemas were not changed.
- Added regression coverage for empty-body parsing across `0-100`, `80-200`, and `300-500` contracts.
- Added regression coverage proving a transient `503` on review regeneration is retried.

## Verification

- Focused worker tests: `python -m pytest services/worker_copy/test_copy_length.py -q` -> `16 passed`.
- Focused campaign tests: `python -m pytest services/campaign_service/test_copy_length_contract.py -q` -> `12 passed`.
- Full worker suite: `python -m pytest services/worker_copy -q` -> `16 passed`.
- Full campaign suite: `python -m pytest services/campaign_service -q` -> `280 passed, 5 skipped, 1 failed`.
- The campaign failure is pre-existing/unrelated: `test_asset_regeneration_sends_complete_v2_image_payload_and_sanitizes_audit` fails before dispatch with `401 Missing authorization token`, and reproduces when run alone. The changed-path focused tests pass.
- Running both service directories in one pytest process is invalid because both expose a top-level `app` package; it causes collection-time cross-service import collisions.

## Scope

Only the worker-copy parser, campaign-service regeneration dispatch calls, their regression tests, and this report were changed by this fix wave. Existing unrelated worktree files were not modified.
