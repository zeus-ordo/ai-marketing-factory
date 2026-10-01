# Task 6 Report

Implemented additive generation diagnostics and single-task retry visibility.

- Campaign API responses now optionally include generation context ID, source counts, token counts/ratios, selected reference IDs, matched folders, external URLs, and sanitized source provenance.
- Campaign tasks expose retry count, failure category/detail, blocked reason, next retry time, provider/model, and generation context ID.
- Review responses and the Review Center expose generation context/source provenance and task failure diagnostics.
- Added Traditional Chinese, English, and Japanese labels for diagnostics, retryability, attempts, and retry states.
- Added a JWT-authorized, company-scoped path to the existing single-task retry operation. The UI retries only the selected failed task and does not independently retry descendants.
- Added loading/empty/error behavior through the existing page and table states; diagnostics are responsive and use accessible section labels and buttons.
- Provenance serialization excludes source text and credentials.

Verification:

- `node scripts/test-campaign-flow-contract.mjs`: passed
- `python -m pytest services/campaign_service -q`: 47 passed
- `npm run build`: passed

## Retry Reconciliation Safeguards

- Dispatch-failure task reconstruction is now guarded end-to-end; store read failures fall back to the authoritative claimed task row for direct persistence reconciliation.
- Run-scoped asset retries require a known asset `run_id` and exact target-run agreement; only an explicit legacy review path may use records without a run.
- Persistence reconciliation now uses `UPDATE ... RETURNING` and reports failure when no claimed retry row was updated, preserving explicit recovery-pending handling.
- Added regressions for store-read failure, missing asset run IDs, and zero-row reconciliation.

Verification:

- `python -m pytest services/campaign_service -q`: 62 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `git diff --check`: passed

## Harden Final Diagnostics Validation

- Worker success validation no longer trusts `displayable_asset_count`; it validates actual asset collections, URLs, and content, including retry reconciliation assets.
- Added regression coverage for inconsistent positive counts with empty asset collections.
- Review hooks now maintain stable order across auth/loading transitions, and diagnostics sections have stable React keys.
- Provenance URL rendering rejects HTTP(S) credentials and only renders safe links.

Verification:

- Campaign service: 78 passed
- Orchestrator: 25 passed
- Worker tests: 3 passed
- Diagnostics contract: passed
- Campaign flow contract: passed
- `npm run build`: passed
- `git diff --check`: passed

## P2 Translation Follow-up

- Replaced newly added diagnostics literals in Campaigns, Review, and the review queue with existing `common.notAvailable` translations and scoped `review.diagnostics` keys.
- Added translated diagnostics units and task-type labels for English, Traditional Chinese, and Japanese.
- Added contract assertions preventing diagnostics `tokens`, `sources`, and em-dash fallback literals from regressing.

Verification:

- `node scripts/test-campaign-diagnostics.mjs`: passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run check:i18n`: reports only pre-existing hardcoded UI findings in Campaigns form/modals and Content Studio.
- `npm run lint`: reports only pre-existing errors in untouched Campaigns form/modals, Review loading/permission text, review preview text, Content Studio, Members, and Roles; edited diagnostics lines have no new findings.
- `python -m pytest services/campaign_service -q`: 78 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `python -m pytest services/worker_image/test_prompt.py -q`: 3 passed
- `python -m pytest -q`: collection blocked by pre-existing cross-service imports (`MAX_RETRY` resolution and worker-image `app.prompt_utils` module path).
- `git diff --check`: passed
- `npm run build`: passed

Concern: existing FastAPI, Pydantic, Node module-type, and Next.js workspace-root warnings remain unrelated to this follow-up.

## Final Diagnostic Translation Fix

- Translated task status values, including `blocked`, through the shared `status.*` locale keys in Campaigns, Review, and the review queue.
- Translated known provenance source types through the shared `ProvenanceList` using `review.diagnostics.sourceTypes.*` keys for English, Traditional Chinese, and Japanese.
- Unknown task statuses and source types safely fall back to the localized `common.notAvailable` value.
- Added contract checks preventing raw diagnostic status/source-type rendering from regressing.

Verification:

- `node scripts/test-campaign-diagnostics.mjs`: passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run check:i18n`: only pre-existing Campaigns form/modal and Content Studio findings
- `python -m pytest services/campaign_service -q`: 78 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `python -m pytest services/worker_image/test_prompt.py -q`: 3 passed
- Touched-file ESLint: only pre-existing Campaigns form/modal, Review loading/permission, and review preview hardcoded-text errors
- `git diff --check`: passed
- `npm run build`: passed

Concern: existing repository lint findings and framework/module warnings remain unrelated and were not changed.
- `npm run lint`: failed on 81 pre-existing repository lint errors and 13 warnings, including existing hardcoded-text violations outside this change

## Complete Review Diagnostics Details

- Review diagnostics now render provenance source type, label, folder, and sanitized clickable HTTP(S) URLs.
- Review task diagnostics now render provider, model, sanitized error details, status, blocked reason, and strict retryability.
- Review retryability never falls back to task status; it requires `retryable === true` and fewer than three attempts.
- Added Review rendering/filtering and retry-gating contract assertions while preserving responsive table/panel layouts and accessible controls.

Verification:

- Campaign service: 77 passed
- Orchestrator: 25 passed
- Worker tests: 3 passed
- Review diagnostics contract: passed
- Campaign flow contract: passed
- `npm run build`: passed
- `git diff --check`: passed

## Complete Diagnostics Presentation Follow-up

- Image `RevisionRequest` now requires `company_id`; both asset regeneration and the review revision caller supply it.
- Added image regeneration schema/endpoint regression coverage and successful provider/model metadata assertions.
- Campaign and Review now show provenance source type, label, folder, safe HTTP(S) URLs, provider/model, and sanitized task error details.
- Added shared diagnostics transforms and contract assertions for URL safety, error redaction, and retry eligibility.
- Retry controls require `retryable === true` and fewer than three attempts.

Verification:

- Campaign service: 77 passed
- Orchestrator: 25 passed
- Worker tests: 3 passed
- Diagnostics contract: passed
- Campaign flow contract: passed
- `npm run build`: passed
- `git diff --check`: passed

## Asset Regeneration Safety Follow-up

- Image asset regeneration payloads now include `company_id` and are validated against `ImageRunRequest` in the regression suite.
- Successful image regeneration persists provider/model metadata alongside the regenerated asset.
- The four supported asset-producing task types reject every successful result without displayable assets, including bare `{"status": "passed"}` results.
- HTTP ingestion returns a failed response for empty results and rejects unknown task types; descendants remain blocked.
- Retry reconciliation includes the validated displayable asset count so legitimate successful retries are not rejected.

Verification:

- Focused campaign tests: 48 passed
- Campaign service: 77 passed
- Orchestrator: 25 passed
- Worker tests: 2 passed
- Contract test: passed
- `npm run build`: passed
- `git diff --check`: passed

## Worker Result Diagnostics Follow-up

- Image generation payloads now include required company identity and preserve retry routing metadata.
- Empty copy/image/video/ads worker results are classified as failed with a retryable diagnostic and cannot unblock descendants.
- Provider/model metadata is retained in copy, image, ads, and video asset records for both primary and retry paths.
- Added HTTP-level worker result coverage and direct payload/schema/metadata regression tests.

Verification:

- Focused route/state tests: 35 passed
- Campaign service: 75 passed
- Orchestrator: 25 passed
- Worker tests: 2 passed
- Contract test: passed
- `npm run build`: passed
- `git diff --check`: passed

## Final Diagnostics Review

- Retry now uses strict worker result handling, preserving durable failure reconciliation when workers return no assets.
- CampaignTask client data includes run and generation context IDs; Review task diagnostics are filtered to each diagnostic group's run/context.
- Provider/model values are accepted by all worker request schemas, propagated through worker responses, asset metadata, and retry persistence.
- Added FastAPI TestClient coverage for Campaign, Review, validation, retry, and cold-cache persistence hydration paths.
- Added field-friendly formatting for FastAPI validation arrays and accessible Review status/rejection controls.

Verification:

- `python -m pytest services/campaign_service -q`: 65 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- Worker tests: 2 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run build`: passed
- `git diff --check`: passed

## Review Run Diagnostics Follow-up

- Retry dispatch now propagates authoritative task/provider/model context and persists provider/model diagnostics from worker output when available.
- In-memory review fallback preserves the source asset/task run ID, including mixed-run campaigns.
- Review diagnostics and task failures are filtered by the diagnostic item's run/context rather than leaking campaign-wide state.
- Added route-level regressions for fallback run identity, mixed-run dispatch scope, and concurrent retry behavior.

Verification:

- `python -m pytest services/campaign_service/test_task6_routes.py services/campaign_service/test_worker_result_state.py -q`: 23 passed
- `python -m pytest services/campaign_service -q`: 63 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run build`: passed
- `git diff --check`: passed
- `npm run build`: passed
- `git diff --check`: passed

## P1 Retry Follow-up

- Added persisted task `run_id` and atomic conditional retry claims with a bounded attempt count; failed state persistence can safely release an unstarted claim.
- Review/asset retry requests resolve the reviewed task and run, use that run's generation snapshot, and dispatch only same-run blocked descendants.
- Added route regressions for Campaign GET/list hydration, Review run serialization, concurrent retry claims, provider/model diagnostics, and mixed-run descendant scope.

Verification:

- `python -m pytest services/campaign_service/test_task6_routes.py services/campaign_service/test_worker_result_state.py -q`: 14 passed
- `python -m pytest services/campaign_service -q`: 54 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run build`: passed
- `git diff --check`: passed

## Endpoint Review Follow-up

- Wired diagnostic enrichment into Campaign GET/list responses and added latest persisted-run hydration for restart compatibility.
- Preserved FastAPI string, array, and object details in `ApiRequestError`; Campaign creation renders useful field-level validation messages.
- Added serialized provider/model fields and endpoint tests for diagnostics, Review run association, and concurrent retry claims.
- Scoped Review task diagnostics to the matching asset task and generation context/run instead of campaign-wide task state.
- Added bounded, locked manual retry claims and descendant-only dispatch coverage.

The build retains existing warnings about FastAPI `on_event` deprecation and multiple lockfiles/workspace-root inference.

## Authoritative Retry Review Fixes

- Manual retry claims now atomically return the authoritative incremented task row, including retry count and run ID, so stale replica records cannot overwrite the claimed state or double-increment attempts.
- Review and asset selectors are now required to resolve, campaign-scoped, task-scoped, and run-scoped; mismatched caller IDs and old/new run combinations return clear 400/404 responses instead of falling back to `task_id`.
- Worker dispatch failures now reconcile a claimed retry through a durable terminal-failure update when the normal task-store write fails; unreconciled failures return an explicit recovery-pending 503.
- Added replica-style claim interleaving, authoritative run/count, invalid selector, campaign/run mismatch, and failure-reconciliation regression tests.

Verification:

- `python -m pytest services/campaign_service -q`: 59 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `git diff --check`: passed
- `npm run build`: passed

## Review Follow-up

- Hydrated latest persisted generation snapshots into Campaign and Review responses, including backward-compatible task diagnostic columns.
- Preserved structured API error details and rendered field-level 422 messages without clearing the form.
- Enforced manual retryability and finite attempts; successful retries dispatch only newly unblocked descendants.
- Changed Review diagnostics to group by campaign/run and render per-item ratios, provenance, provider, model, and task failure details.
- Added behavior coverage for diagnostics serialization and retry eligibility.

Verification after review follow-up:

- `python -m pytest services/campaign_service -q`: 49 passed
- `python -m pytest services/orchestrator -q`: 25 passed
- `node scripts/test-campaign-flow-contract.mjs`: passed
- `npm run build`: passed
- `git diff --check`: passed
