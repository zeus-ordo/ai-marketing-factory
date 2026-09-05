# Task 3 Report

## Changed Files

- `services/campaign_service/app/persistence.py`: additive `folders` schema, scoped uniqueness indexes, nullable association columns, folder CRUD, and durable `folder_id` persistence for knowledge items and campaign references.
- `services/campaign_service/app/main.py`: scoped folder models/routes, JWT/company authorization, platform read/use-only behavior, folder-aware knowledge/reference payloads, and platform knowledge visibility.
- `lib/api/campaigns.ts`: folder API/types and `folder_id` upload/update/reference contracts.
- `app/content-studio/page.tsx`: backend folder loading, creation/deletion, folder selection, associations, and platform read-only display.
- `app/campaigns/page.tsx`: backend folder loading, read-only labels, and folder-aware knowledge/reference operations.
- `app/api/folders/route.ts`: removed obsolete local filesystem route.
- `app/api/folders/[name]/route.ts`: removed obsolete local filesystem route.
- `scripts/test-folder-scope-contract.mjs`: frontend/API contract check.
- `services/campaign_service/test_folder_scope.py`: scope and authorization tests.
- `services/campaign_service/test_reference_folder_association.py`: association persistence tests.
- `services/campaign_service/test_persistence_migrations.py`: additive migration test.
- `lib/server/folders-store.ts`: retained; it is no longer used by the UI or folder API routes.

## TDD Evidence

- RED: focused tests initially failed 5 tests for the missing authorization helper, migration, and `folder_id` persistence behavior.
- GREEN: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py -q` passed 5 tests.
- GREEN regression: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_task6_routes.py -q` passed 27 tests.
- Frontend contract: `node scripts/test-folder-scope-contract.mjs` passed.

## Verification

- `npm run lint`: passed with 0 errors and 13 pre-existing warnings.
- `npm run build`: passed.
- `python -m compileall ...`: passed.
- `git diff --check`: passed.
- `npm run check:secrets`: blocked by existing weak/default values in `.env.local` and `.env.test.local`; no secrets were added or exposed.
- Full campaign-service suite: 103 passed, 1 failed when run as a combined suite because `test_campaign_validation.py::test_invalid_campaign_is_not_persisted` received 401 instead of 422 after another test mutated the internal API key; the test passes in isolation.

## Deployment and Migration Concerns

- Run the additive schema initialization against a backup before deployment. Existing folder text/category data remains readable; `folder_id` stays nullable where inference is unsafe.
- Verify platform/company normalized-name uniqueness conflicts before enabling writes.
- Confirm `CHATBOT_INTERNAL_API_KEY`, `PLATFORM_ADMIN_KEY`, JWT configuration, and campaign-service connectivity in deployment environments.
- Keep `lib/server/folders-store.ts` until production backend reads and association persistence are verified across restart; it was intentionally not deleted in this task.
