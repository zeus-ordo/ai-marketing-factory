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

## Reviewer Fix Report

### Changed Files

- `services/campaign_service/app/main.py`: require authenticated campaign-company access for reference upload/list/download; reject deletion of folders with persisted knowledge/reference associations.
- `services/campaign_service/app/persistence.py`: add durable association counting and deterministic legacy text inference helper.
- `services/campaign_service/test_reference_scope.py`: cover unauthenticated, cross-company, same-company, and internal reference-list access.
- `services/campaign_service/test_folder_scope.py`: cover referenced-folder deletion rejection.
- `services/campaign_service/test_reference_folder_association.py`: cover repository association-count query.
- `services/campaign_service/test_persistence_migrations.py`: cover deterministic legacy inference and explicit unfiled fallback.
- `app/content-studio/page.tsx`: use `folder_id` for selection, upload, filtering, and moves; exclude platform folders from move targets.
- `app/campaigns/page.tsx`: use folder IDs for reference filtering and knowledge moves; exclude platform folders from mutation targets.
- `scripts/test-folder-scope-review-contract.mjs`: assert no name-only folder resolution and platform read-only UI behavior.

### TDD Evidence

- RED: the new focused command initially failed 5 tests: 3 missing production behaviors, 1 missing persistence helper, and 1 missing legacy helper; the same run also exposed 2 incomplete test-fixture errors, which were corrected before implementation verification. The UI contract failed on existing name-only lookups.
- GREEN: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_scope.py services/campaign_service/test_task6_routes.py -q` passed **33 tests**, with 2 framework deprecation warnings.
- GREEN: `node scripts/test-folder-scope-review-contract.mjs` passed.
- GREEN: `git diff --check` passed.

### Verification and Concerns

- `npm run lint` passed with 0 errors and 13 existing warnings.
- `npm run build` passed. Next.js reported the existing multiple-lockfile workspace-root warning.
- `npm run check:secrets` remains blocked by pre-existing weak/default values in `.env.local` and `.env.test.local`; no secrets were added or exposed.
- Legacy text is preserved as the response fallback; `legacy_folder_id` only infers an ID for one case-insensitive match and returns `None` for ambiguous/general/unfiled values. A production backfill should run after conflict review.
- `lib/server/folders-store.ts` remains retained until deployed backend reads and restart persistence are verified.
