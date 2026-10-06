# Task 3 Report

Status: complete

Commit: `384c2d5` (implementation), with this report in the follow-up documentation commit.

Implemented upload-time image analysis records, best-effort Redis enqueueing with short-lived deduplication, safe analysis status and retry routes, reference-pack enqueueing, and orchestrator dispatch to `WORKER_ENRICHMENT_URL/internal/v1/image-enrichment` using the existing stream claim and acknowledgement path.

Tests:

- `python -m pytest services/campaign_service -q`: 216 passed, 5 skipped.
- `python -m pytest services/orchestrator -q`: 28 passed.
- Focused Task 3, Task 1, batch-upload, and migration tests passed.
- `python -m compileall -q services/campaign_service/app services/orchestrator/app`: passed.
- `git diff --check`: passed.

Concerns:

- The campaign and orchestrator suites must be run from their service directories, or the repository root with an explicit service path, because both use a top-level `app` test-import convention.
- Existing FastAPI deprecation warnings for `on_event` remain.

## Review Fixes

- Enrichment worker requests now send `X-Internal-Api-Key` from the existing internal key configuration.
- Enrichment failures now carry a durable stream retry counter, retry through `MAX_RETRY`, publish terminal failures to the DLQ, and ACK only after the same final lease ownership check as normal tasks.
- Public Knowledge item sanitization now recursively removes `stored_path`; in-memory Reference Pack rows retain the pending analysis summary.

Follow-up verification:

- Campaign focused, batch-upload, Task 1, and migration tests: 37 passed, 3 skipped.
- Orchestrator failure-isolation tests: 30 passed.
- Compile and diff checks passed.
