# Task 3 Report

## Changed Files

- `services/campaign_service/app/main.py`
  - Kept campaign access authorization before any upload byte read.
  - Added stable authorization, extension, MIME, size, timeout, and persistence error codes.
  - Added bounded chunked writes and cleanup for validation, timeout, filesystem, and persistence failures.
  - Removed the persistence-failure fallback that created an in-memory success/orphan file.
  - Kept successful responses limited to reference and folder metadata, with a relative download URL.
- `services/campaign_service/test_batch_upload.py`
  - Added the six required tests plus MIME mismatch coverage.
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-3-report.md`
  - This report.

## Red/Green Evidence

Red run before production changes:

```text
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py -q
4 failed, 5 passed, 2 warnings
```

The failures covered legacy validation messages, persistence failure being swallowed, missing MIME validation, and the initial cleanup assertion.

Green focused run:

```text
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py -q
10 passed, 2 warnings
```

Green required verification run:

```text
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py services/campaign_service/test_reference_folder_association.py -q
12 passed, 1 skipped, 2 warnings
```

Additional verification:

```text
python -m compileall -q services/campaign_service
```

Completed successfully with no output. `git diff --check` also completed successfully; Git emitted only its LF-to-CRLF working-copy warning.

## Concerns

- The folder association integration test remains skipped unless `CAMPAIGN_TEST_DATABASE_URL` is configured.
- Pytest reports the existing `pytest-asyncio` loop-scope warning and FastAPI `on_event` deprecation warnings.
- Full campaign-service and end-to-end suites were not run because this task brief specifies the focused upload/scope/folder verification commands.

## Review Findings Follow-Up

Added regression coverage for directory creation failure, generic stream failure, upload deadline timeout, octet-stream incompatibility, and partial database persistence cleanup. The upload directory creation now runs inside the sanitized cleanup boundary; all generic stream/write exceptions return `PERSISTENCE_ERROR`; the bounded loop enforces `REFERENCE_UPLOAD_TIMEOUT_SECONDS` and returns `UPLOAD_TIMEOUT`; octet-stream is limited to an explicit office-document extension allowlist; and persistence failures invoke the repository delete hook before returning.

Red run before the follow-up production changes:

```text
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py services/campaign_service/test_reference_folder_association.py -q
6 failed, 11 passed, 1 skipped, 2 warnings
```

Green follow-up run:

```text
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py services/campaign_service/test_reference_folder_association.py -q
17 passed, 1 skipped, 2 warnings
```
