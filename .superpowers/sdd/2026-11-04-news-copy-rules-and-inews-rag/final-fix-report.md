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
