# Task 4 Report

Status: complete

Implemented measurable generation context assembly and persistence.

- Added deterministic UTF-8 byte based token estimation, documented in `context_assembler.py`.
- Enforced internal `floor(total_budget * 0.75)` and external remainder budgets without source relabeling.
- Added source ranking and provenance preservation for IDs, folders, URLs, providers, queries, and retrieval timestamps.
- Added additive immutable PostgreSQL snapshot tables and persistence.
- Created one snapshot before campaign dispatch and passed its ID through worker payloads and supported asset metadata.
- Integrated automatic Task 3 external search with classified failure statuses and internal-only fallback.

Verification:

- `python -m pytest services/campaign_service/test_context_assembler.py -q`: 5 passed.
- `python -m pytest services/campaign_service -q`: 34 passed.
- `python -m compileall -q services/campaign_service/app`: passed.
- `git diff --check`: passed.
- `npm run build`: passed.

Concern: the existing project emits FastAPI `on_event` deprecation warnings during tests; this task does not alter that unrelated behavior.
