# Final Fix Report

## Status

`FIXED_AND_VERIFIED`.

All four findings in `final-fix-brief.md` were addressed in the isolated
worktree. No production endpoint was called.

## Fixes

1. Importer authentication now reads credentials only from environment
   variables. Bearer tokens use `Authorization: Bearer ...`; platform admin
   keys use the existing campaign-service `x-platform-key` convention. The
   CLI supports `--bearer-token-env` and `--admin-key-env` to select variable
   names, never credential values. Dry-run exits before auth lookup/request.
2. Uploaded items are polled with configurable `--poll-interval-seconds`
   and `--readiness-timeout-seconds`. Each item records `ready`, `failed`,
   `timeout`, or `poll-failed` in the report.
3. News remains `1000-1400`. Social was restored to `100-200`, advertising
   was restored to max `100`, and the campaign policy/tests were corrected.
4. Same-title items are skipped only when an exact SHA-256 is available in
   metadata or embedded provenance. Missing or mismatched metadata uploads the
   content instead of silently skipping it. If the metadata list request
   fails, the importer proceeds with uploads and records a warning.

## Manual Invocation

Authenticated bearer-token example (credential supplied out of band):

```text
INEWS_IMPORT_BEARER_TOKEN=<token> python scripts/import_inews_references.py --source-dir <dir> --api-base-url <url> --report <report.json>
```

Platform-admin-key example:

```text
PLATFORM_ADMIN_KEY=<key> python scripts/import_inews_references.py --source-dir <dir> --api-base-url <url> --report <report.json> --admin-key-env PLATFORM_ADMIN_KEY
```

Use `--dry-run` to verify scanning/report output without credentials or HTTP.
Do not pass credentials as command-line values and do not run these examples
against production during local verification.

## Focused Tests

- `python -m pytest scripts/test_import_inews_references.py -q`: **13 passed**
- `python -m pytest services/campaign_service/test_copy_length_contract.py -q`: **12 passed**, 2 existing FastAPI deprecation warnings
- `python -m pytest services/campaign_service/test_industry_matching.py -q`: **11 passed**, 2 existing FastAPI deprecation warnings
- `python -m pytest services/worker_copy/test_copy_length.py -q`: **22 passed**

## Concerns

- The test environment emits the repository's existing pytest-asyncio and
  FastAPI `on_event` deprecation warnings.
- Readiness status depends on the reference-pack API's `analysis_status`
  field; request failures are reported as `poll-failed` rather than retried
  indefinitely.

## P1 Follow-up

Status: `FIXED_AND_VERIFIED` for both requested findings.

- Initial copy generation now explicitly treats iNews references as style and
  structure only, grounds factual claims in the campaign brief and approved
  inputs, prohibits copying names, numbers, and quotes, and requires gaps to be
  stated instead of invented.
- Text embedding recovery now exposes chunk counts to the worker, reclaims a
  ready chunk 0 when expected chunks are missing or non-ready, and rebuilds all
  chunks through the existing upsert path. Fully ready embeddings remain
  idempotent, while pending/failed retry and image processing paths are
  unchanged.

Focused verification:

- `python -m pytest services/campaign_service/test_industry_matching.py services/campaign_service/test_context_assembler.py -q`: 46 passed, 1 unrelated pre-existing JWT fixture failure.
- `python -m pytest services/worker_copy/test_copy_length.py -q`: 25 passed.
- `python -m pytest services/worker_enrichment/test_text_embedding_job.py services/worker_enrichment/test_enrichment_job.py -q`: 13 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py -q`: 8 passed.

No production services or databases were called.

## Token Budget Follow-up

- Updated `_completion_token_budget` to use a bounded `3x` multiplier with a
  minimum of `512` and a safety cap of `4096`. A `1400`-character news release
  now receives `4096` completion tokens instead of `1656`; ordinary ranges stay
  bounded by the same minimum and cap.
- Added parameterized regression coverage for minimum, ordinary, long-form,
  and oversized body ranges. Existing prompt, repair, and request behavior was
  otherwise unchanged.
- TDD RED: the updated budget test failed 3 cases under the old additive
  formula (`200`, `500`, and `1400` body lengths).
- TDD GREEN: `python -m pytest services/worker_copy/test_copy_length.py -q` ->
  **29 passed**.
- Full worker-copy verification: `python -m pytest services/worker_copy -q` ->
  **29 passed**.
- `git diff --check` passed; Git emitted only its existing LF/CRLF conversion
  warnings.

## Dynamic Long-Form Repair Follow-up

- Fixed the P1 range inconsistency in `services/worker_copy/app/main.py`.
- Repair section ranges now derive from the requested long-form contract's safe
  interior range. The approved 1000-1400 contract still targets 1100-1300;
  a 1400-1600 contract now targets a satisfiable 1500-character allocation.
- Added regression coverage for the 1400-1600 contract, including exact sum
  checks across all five section ranges and successful expanded-response
  acceptance.
- TDD RED: the new 1400-1600 test failed because the repair prompt retained
  the hard-coded 1100-1300 total.
- TDD GREEN: `python -m pytest services/worker_copy/test_copy_length.py -q` ->
  **31 passed**.
- No production services or databases were called.

## Narrow-Range Allocation Follow-up

- Replaced proportional section rounding with a safe integer partition of each
  satisfiable target total across five sections.
- Added a boundary sweep covering valid minimum/maximum pairs, including the
  previously failing 1017-1018 contract. Every section now has integer,
  non-reversed bounds and the five bounds sum to the target totals.
- Preserved the 1000-1400 interior target of 1100-1300 and the 1400-1600
  target of 1500-1500.
- TDD RED: the boundary sweep failed under the prior proportional rounding
  because a narrow range produced a reversed section range.
- TDD GREEN: `python -m pytest services/worker_copy/test_copy_length.py -q` ->
  **32 passed**.
- No production services or databases were called.
