# Task 1 Report: Image Analysis Persistence

## Files Changed

- `services/campaign_service/app/persistence.py`
  - Added `knowledge_item_image_analysis` migration and status/index fields.
  - Added safe optional pgvector migration with JSONB fallback.
  - Added create, claim, complete, fail, get, and ready-list persistence methods.
  - Added safe analysis summaries to Knowledge item listings.
- `services/campaign_service/app/schemas.py`
  - Added `ImageAnalysisRecord` and public `KnowledgeItemAnalysisSummary` models.
- `services/campaign_service/app/main.py`
  - Exposed the safe analysis summary on `KnowledgeItemRecord`.
- `services/campaign_service/app/image_enrichment.py`
  - Added status/version constants and recursive validation for JSON-only safe attributes.
- `services/campaign_service/test_image_enrichment_persistence.py`
  - Added lifecycle and schema tests.
- `services/campaign_service/test_persistence_migrations.py`
  - Added migration assertions for the analysis table and index.

## Test Commands

```text
python -m pytest services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py -q
3 passed, 4 skipped, 2 warnings in 0.66s

python -m compileall -q services/campaign_service/app services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py
git diff --check
```

The four persistence lifecycle tests are skipped because `CAMPAIGN_TEST_DATABASE_URL` is not configured. The warnings are existing pytest-asyncio configuration and FastAPI lifecycle deprecation warnings.

## Scope

No provider, queue, worker endpoint, retrieval, or UI implementation was added.

## Concerns

- Real PostgreSQL lifecycle coverage remains pending until a disposable database is configured.
- The optional vector column is attempted inside a savepoint; JSONB embedding storage remains available when pgvector is unavailable.

## Review Fix

- Hardened the shared image attribute validator to allow only bounded JSON primitives, lists, and string-keyed dictionaries; it rejects private/storage/path/base64/binary fields and values, arbitrary objects, sets, tuples, dates, non-finite numbers, and oversized values.
- Added the same validator to the public analysis schemas.
- Added tests for ready-item listing, rejected unsafe/non-JSON attributes, and public schema validation.

```text
python -m pytest services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py -q
12 passed, 3 skipped, 2 warnings in 0.69s

python -m compileall -q services/campaign_service/app services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py
git diff --check
```

The three PostgreSQL lifecycle tests remain skipped because `CAMPAIGN_TEST_DATABASE_URL` is not configured; no database success was fabricated.

## Second Review Fix

- Added explicit relative/private path detection and short binary-base64 detection, including `AAAA`, while retaining natural-language values containing ordinary punctuation.
- Made `list_knowledge_items` tolerate legacy nine-column mock rows by only reading analysis fields when the new columns are present.
- Added regression coverage for short base64, relative paths, natural language, and legacy knowledge-row round trips.

```text
python -m pytest services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py -q
16 passed, 3 skipped, 2 warnings in 0.67s

python -m pytest services/campaign_service/test_reference_folder_association.py services/campaign_service/test_llm_context_capture.py services/campaign_service/test_reference_packs.py -q
31 passed, 2 skipped, 2 warnings in 0.71s

python -m compileall -q services/campaign_service/app services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_folder_association.py
git diff --check
```

PostgreSQL-dependent tests remain skipped when `CAMPAIGN_TEST_DATABASE_URL` is unset.
