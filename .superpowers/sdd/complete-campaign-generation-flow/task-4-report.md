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

## Review Fix Report

Fixed all requested Task 4 findings:

- Propagated `generation_context_id` through orchestrator worker requests/results, retry, single-asset generation, and asset metadata.
- Serialized retrieved timestamps as ISO strings and retained classified search errors without preventing persistence.
- Made snapshot source metadata immutable at the application boundary and added insert-only persistence with required task/reference/folder provenance fields.
- Appended the exact snapshot source content to worker prompts.
- Applied the required source priority consistently.
- Made incomplete external-search configuration fall back to classified internal-only context without import failure.
- Restored focused tests for serialization, required fields, immutability, ranking, prompt propagation, and fallback.

Fix verification:

- `python -m pytest services/campaign_service/test_context_assembler.py -q`: 6 passed.
- `python -m compileall -q services/campaign_service/app services/orchestrator/app`: passed.
