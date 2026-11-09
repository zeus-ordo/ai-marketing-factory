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
- Added ready-only text embedding search; deterministic bounded text excerpt assembly remains available as the fallback path.
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

## Review Fixes

The follow-up review findings are addressed as follows:

1. Text context now attempts ready-only semantic retrieval through `TEXT_RAG_QUERY_EMBEDDING`, merges provenance from active platform Reference Pack rows, and deterministically sorts bounded text excerpts when vector retrieval is unavailable.
2. Both campaign persistence and the worker persistence adapter write JSON and attempt the pgvector column under savepoints. `pgvector_available` is exposed by campaign health and remains false when the extension/write path is unavailable.
3. Text worker failures still persist sanitized retryable failure state, then re-raise so the worker endpoint returns a transport failure and the orchestrator retry/DLQ path handles it.
4. Local deployment mounts an idempotent `CREATE EXTENSION vector` init script and requires the extension in the Postgres healthcheck.
5. Added tests for partial chunk failure, ready-job idempotence, orchestrator retry and DLQ, vector writes, context semantic retrieval/fallback, mixed status aggregation, and reset/list persistence contracts.
6. Mixed chunk status is deterministic: failed wins, complete ready chunks produce ready, processing wins over pending, and incomplete rows remain pending.
7. Added `reset_text_embedding_for_retry` and `list_text_embeddings` persistence methods.

## Review-Fix Verification

- `python -m pytest services/worker_enrichment/test_text_embedding_job.py services/worker_enrichment/test_enrichment_job.py -q`: 11 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py services/campaign_service/test_reference_pack_text.py services/campaign_service/test_persistence_migrations.py -q`: 21 passed.
- `python -m pytest services/orchestrator/test_task_failure_isolation.py -q`: 35 passed.
- `python -m pytest scripts/test_import_inews_references.py -q`: 14 passed.
- `python -m pytest services/worker_enrichment/test_provider_contract.py -q`: 17 passed.
- `python -m compileall -q services/campaign_service/app services/worker_enrichment/app services/orchestrator/app`: passed.

One unrelated pre-existing context-suite test remains failing because its synthetic request supplies only `x-internal-api-key` while the regeneration path requires JWT authorization: `test_asset_regeneration_sends_complete_v2_image_payload_and_sanitizes_audit`.

## Scoped Context Review Fixes

- Semantic text results are now admitted only when their item ID exists in the already-filtered active `pack_context`, preserving platform/industry pack scope and provenance.
- Unrelated semantic rows cause deterministic fallback rather than entering campaign context.
- All vector/DB retrieval exceptions are caught, logged using only the exception type, and routed to the bounded deterministic excerpt path so generation continues.
- Added failing-first regression coverage for unrelated semantic result exclusion and generic database retrieval failure fallback.

Verification:

- `python -m pytest services/campaign_service/test_text_embedding_contract.py::test_text_context_uses_ready_semantic_results_and_fallback services/campaign_service/test_text_embedding_contract.py::test_text_context_falls_back_deterministically_when_semantic_unavailable -q`: 2 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py services/campaign_service/test_reference_pack_text.py services/campaign_service/test_context_assembler.py -q`: 52 passed, 1 unrelated pre-existing JWT fixture failure.
- `python -m pytest services/campaign_service/test_image_rag_retrieval.py services/campaign_service/test_image_enrichment_routes.py -q`: 24 passed.
- `git diff --check`: passed.

## Provenance Contract Fix

- TXT/MD upload handling now parses only the non-sensitive `source` and valid 64-character `sha256` headers into `provenance_source` and `provenance_sha256` metadata.
- `ReferencePackItemRecord` exposes only those two safe provenance fields at the top level; private `stored_path`, raw metadata, tokens, and local paths remain excluded.
- The iNews importer now matches the actual pack-item response fields (`provenance_sha256` and `provenance_source`) instead of hidden `metadata.sha256` or unavailable content/provenance fields.
- Added failing-first tests for the actual API response shape and same-title/hash rerun idempotence.

Verification:

- `python -m pytest services/campaign_service/test_reference_pack_text.py services/campaign_service/test_reference_packs.py services/campaign_service/test_persistence_migrations.py -q`: 42 passed.
- `python -m pytest scripts/test_import_inews_references.py -q`: 14 passed.
- `python -m compileall -q services/campaign_service/app scripts/import_inews_references.py`: passed.
- `git diff --check`: passed.

## Final Review Fixes

- Deterministic text fallback now admits only text rows with `embedding_status=ready`, a positive `chunk_count`, and `ready_chunk_count >= chunk_count`; pending, processing, and failed TXT/MD rows stay out of RAG while active pack and industry scope remains enforced.
- Image and video worker payloads now omit text from serialized context sources and `text_references`; copy and ads payloads retain ready text RAG references.
- Updated `docs/admin-reference-packs-manual.txt` to document TXT/MD `embedding_status` values and ready-chunk requirements, explicitly separating them from image `analysis_status`.
- Added regression tests for ready-only fallback and text exclusion from image/video payloads, and updated the existing text-context fixture to declare its content ready.

Verification:

- `python -m pytest services/campaign_service/test_text_embedding_contract.py -q`: 8 passed.
- `python -m pytest services/campaign_service/test_image_generation_contract.py -q`: 28 passed.
- `python -m pytest services/campaign_service/test_context_assembler.py::test_platform_text_reference_enters_rag_context_without_image_quota_usage -q`: 1 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py services/campaign_service/test_image_generation_contract.py -q`: 36 passed.
- Existing context suite still has the unrelated JWT fixture failure in `test_asset_regeneration_sends_complete_v2_image_payload_and_sanitizes_audit`.

## Final Video Prompt Fix

- `snapshot_prompt_context` now accepts the task type and excludes TXT/MD snapshot entries for image and video generation while preserving image/visual entries.
- Direct video worker payloads, queued generation, and video regeneration all use the task-aware snapshot filter, preventing unfiltered `context_text` from reintroducing text references.
- Added a failing-first regression proving video prompts omit TXT/MD content while retaining visual snapshot context.

Verification:

- `python -m pytest services/campaign_service/test_image_generation_contract.py -q`: 29 passed.
- `python -m pytest services/campaign_service/test_text_embedding_contract.py services/campaign_service/test_context_assembler.py -q`: 42 passed, 1 unrelated pre-existing JWT fixture failure.
- `python -m pytest services/campaign_service/test_industry_matching.py services/campaign_service/test_image_rag_retrieval.py -q`: 26 passed.
- `python -m compileall -q services/campaign_service/app`: passed.
- `git diff --check`: passed.
