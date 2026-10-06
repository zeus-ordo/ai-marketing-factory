# Task 2 Report

## Status

Complete. Implemented the isolated asynchronous image enrichment worker only. Queue/orchestrator wiring, uploads, retrieval, UI, and deployment compose changes were not modified.

## Files

- `services/worker_enrichment/app/main.py`: health endpoint, authenticated internal enrichment endpoint, idempotent job processing, PostgreSQL persistence boundary.
- `services/worker_enrichment/app/providers.py`: multimodal analysis and embedding interfaces/adapters, strict attribute/vector validation, transient image encoding.
- `services/worker_enrichment/requirements.txt`
- `services/worker_enrichment/Dockerfile`
- `services/worker_enrichment/test_provider_contract.py`
- `services/worker_enrichment/test_enrichment_job.py`
- `services/campaign_service/app/image_enrichment.py`: canonical attribute text and redacted provider error contracts.

## Commits

- `de2172f feat: add asynchronous image enrichment worker`
- `e2449ef fix: keep enrichment image paths private`

## Verification

- `py -m pytest services/worker_enrichment/test_provider_contract.py services/worker_enrichment/test_enrichment_job.py -q`: `6 passed`
- `py -m pytest services/campaign_service/test_image_enrichment_persistence.py -q`: `13 passed, 3 skipped` (database fixture unavailable)
- `python -m compileall -q services/worker_enrichment services/campaign_service/app/image_enrichment.py`: passed
- `git diff --check`: passed; only Git line-ending normalization warnings were emitted.

## Concerns

- End-to-end PostgreSQL persistence was not exercised because `CAMPAIGN_TEST_DATABASE_URL` is not configured.
- Provider endpoints are configurable through environment variables and require compatible upstream `/analyze` and `/embeddings` APIs.
- The worker requires `CAMPAIGN_DATABASE_URL` or `DATABASE_URL` at runtime.

## Review Fixes

Applied worker-only review corrections:

- Added `services/shared/image_enrichment.py` as the strict validator source and included it in the worker image; the worker no longer contains a weaker fallback validator. Runtime tests cover absolute/relative paths, base64, and binary fields.
- Changed persistence lookup to query `(item_id, analysis_version)` directly and added a multiple-version regression test.
- Internal enrichment requests now require a configured internal API key; missing configuration is rejected with `401` before persistence or provider work.
- Provider error codes are mapped to a fixed safe allowlist; arbitrary exception `.code` values are never persisted.

Fix verification:

- Worker focused tests: `13 passed`
- Task 1 persistence tests: `13 passed, 3 skipped`
- Compile check: passed
- Diff check: passed

## Standalone Build Context Fix

The repository's service convention builds each Dockerfile with its own service directory as context and copies local `app` only. The previous repository-level `shared` path was not available in that context and has been removed.

- Added identical strict `app/safe_attributes.py` contract modules to `worker_enrichment` and `campaign_service`.
- Updated worker and Task 1 imports to use their local contract module.
- Removed the invalid `COPY shared` instruction.
- Added a subprocess test that imports the worker from `services/worker_enrichment` without the repository root and rejects private paths, relative paths, and base64 data.
- Verified the two contract modules have identical SHA-256 content.

Final verification:

- Worker suite: `14 passed`
- Task 1 persistence tests: `13 passed, 3 skipped`
- Standalone import and validator hash check: passed
- Compile check: passed
- Diff check: passed
- Docker build was attempted from `services/worker_enrichment` but could not connect because the local Docker daemon is not running.
