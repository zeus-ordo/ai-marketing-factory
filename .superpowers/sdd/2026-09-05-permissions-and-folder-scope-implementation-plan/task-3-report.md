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

## Latest Reviewer Fix Report

### Changed Files

- `services/campaign_service/app/main.py`: activate deterministic legacy category inference in knowledge/reference list responses; align in-memory folder deletion safety and internal platform-only listing with persistence.
- `app/campaigns/page.tsx`: use scope/company/folder ID keys for knowledge grouping and selection, and exclude platform folders from move targets.
- `services/campaign_service/test_folder_scope.py`: cover in-memory association rejection and internal listing scope.
- `services/campaign_service/test_persistence_migrations.py`: cover ambiguous scoped-name fallback and production list-response inference.
- `services/campaign_service/test_reference_folder_association.py`: add real repository reload test using `PostgresPersistence` when `CAMPAIGN_TEST_DATABASE_URL` is available.
- `scripts/test-folder-scope-review-contract.mjs`: assert duplicate-safe folder keys, company scope retention, folder-ID filtering, and platform mutation exclusion.

### TDD Evidence

- RED: focused tests failed 3 expected behaviors for inactive legacy conversion, in-memory deletion/listing divergence, and the new grouping contract. A fixture-only timestamp error was corrected before implementation verification.
- GREEN: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_scope.py services/campaign_service/test_task6_routes.py -q` passed **36 tests**, with 1 optional real-DB reload test skipped and 2 framework deprecation warnings.
- GREEN: `node scripts/test-folder-scope-review-contract.mjs` passed.
- GREEN: `git diff --check` passed.

### Verification and Concerns

- `npm run lint` passed with 0 errors and 13 existing warnings.
- `npm run build` passed; Next.js emitted the existing multiple-lockfile workspace-root warning.
- `npm run check:secrets` remains blocked by pre-existing weak/default values in local environment files; no secrets were added or exposed.
- The real persistence reload test requires a disposable PostgreSQL URL because the production abstraction is PostgreSQL-specific; without `CAMPAIGN_TEST_DATABASE_URL` it is skipped and documented rather than using a recording cursor.
- Legacy inference is intentionally conservative: one case-insensitive match only; ambiguous, General, and Unfiled values remain `folder_id=None`.

## Final Reviewer Fix Report

### Changed Files

- `services/campaign_service/app/main.py`: preserve explicit nullable `folder_id` in in-memory knowledge updates and mutate cached reference `folder_id` alongside its legacy label.
- `app/campaigns/page.tsx`: pass folder IDs to the read-only label helper.
- `services/campaign_service/test_folder_scope.py`: exercise in-memory knowledge and reference mutation responses/state.
- `scripts/test-folder-scope-review-contract.mjs`: assert label calls use folder IDs rather than names.

### TDD Evidence

- RED: fallback mutation tests failed before implementation because knowledge response/cache retained `folder_id=None`, reference cache retained `folder_id=None`, and the UI contract found `getKnowledgeFolderLabel(folder.name)`.
- GREEN: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_scope.py services/campaign_service/test_task6_routes.py -q` passed **38 tests**, skipped 1 optional database reload test, and emitted 2 framework deprecation warnings.
- GREEN: `node scripts/test-folder-scope-review-contract.mjs` passed.
- GREEN: `npm run lint` passed with 0 errors and 13 existing warnings.
- GREEN: `npm run build` passed.
- GREEN: `git diff --check` passed.

### Concerns

- The real restart/reload test remains skipped without `CAMPAIGN_TEST_DATABASE_URL`; with that variable it writes and reloads through `PostgresPersistence` rather than a recording cursor.
- Secret scanning remains blocked by pre-existing weak/default local environment values; no secrets were added or exposed.
- Unrelated worktree modifications remain unstaged and preserved.

## Final Reference Scope Fix Report

### Changed Files

- `services/campaign_service/app/main.py`: apply conservative legacy folder inference to in-memory reference listings; preserve existing `folder_id` for omitted PATCH fields while allowing explicit null clearing.
- `app/campaigns/page.tsx`: group references with scope/company/folder-ID keys and keep folder labels keyed by folder ID.
- `services/campaign_service/test_folder_scope.py`: cover in-memory reference inference and omitted-versus-null reference PATCH behavior.
- `scripts/test-folder-scope-review-contract.mjs`: assert reference grouping uses folder keys and label calls receive folder IDs.

### TDD Evidence

- RED: focused tests failed 2 fallback behaviors (legacy reference inference and omitted PATCH association preservation), and the UI contract failed on reference name-only grouping/label usage.
- GREEN: `python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_scope.py services/campaign_service/test_task6_routes.py -q` passed **41 tests**, skipped 1 optional database reload test, and emitted 2 framework deprecation warnings.
- GREEN: `node scripts/test-folder-scope-review-contract.mjs` passed.
- GREEN: `npm run lint` passed with 0 errors and 13 existing warnings.
- GREEN: `npm run build` passed.
- GREEN: `git diff --check` passed.

### Concerns

- The optional real reload test requires `CAMPAIGN_TEST_DATABASE_URL`; without it, the test is skipped because the production repository abstraction is PostgreSQL-specific.
- Secret scanning remains blocked by pre-existing weak/default local environment values; no secrets were added or exposed.
- Unrelated worktree modifications remain unstaged and preserved.
