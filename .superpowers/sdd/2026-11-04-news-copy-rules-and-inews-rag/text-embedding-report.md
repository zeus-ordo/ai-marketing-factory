# Text Embedding Report

## Status

Implemented the approved TXT Reference Pack text-embedding vertical slice in the isolated `news-copy-inews` worktree. Image analysis remains on its existing state table and queue path.

## Changes

- Added `knowledge_item_text_embeddings` persistence with `text-rag-v1`, content SHA, chunk counters, JSON embeddings, optional pgvector column, model/dimension, retry/error fields, and claim/complete/fail methods.
- TXT and MD Reference Pack uploads create pending text state and best-effort enqueue `task.text_embedding`; Redis failure leaves durable pending state.
- Added UTF-8 worker reading, bounded deterministic paragraph chunking, provider validation, per-chunk persistence, all-chunks-ready completion, retryable failure, and idempotent ready handling.
- Added orchestrator topic dispatch, worker endpoint, retry, and DLQ handling for text embedding.
- Added API fields `embedding_status`, `embedding_version`, `ready_chunk_count`, and `chunk_count` without exposing private paths.
- Updated iNews importer readiness polling to use text embedding status rather than image analysis status.
- Added ready-only text embedding search and filtered pending/failed text items from Reference Pack context assembly.
- Switched local Postgres deployment to `pgvector/pgvector:pg16`; persistence records vector availability instead of assuming it.

## Tests

- `python -m pytest services/worker_enrichment/test_text_embedding_job.py -q`: 2 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py -q`: 2 passed.
- `python -m pytest scripts/test_import_inews_references.py -q`: 14 passed.
- `python -m pytest services/orchestrator/test_task_failure_isolation.py -q`: 33 passed.
- `python -m pytest services/worker_enrichment/test_enrichment_job.py services/worker_enrichment/test_provider_contract.py -q`: 24 passed.
- `python -m pytest services/campaign_service/test_reference_pack_text.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_image_enrichment_routes.py -q`: 25 passed.
- `python -m compileall -q services/campaign_service/app services/worker_enrichment/app services/orchestrator/app scripts/import_inews_references.py`: passed.

The service test suites were run separately because their `app` module names collide, as required. No production services were called.

## Concerns

- Existing FastAPI startup deprecation warnings remain unchanged.
- pgvector remains optional at runtime; JSON embeddings remain durable when the extension is unavailable, and vector availability is exposed on persistence rather than silently claimed.
- The current semantic search method is persistence-facing; broader query-embedding orchestration can build on it without changing image analysis state.
