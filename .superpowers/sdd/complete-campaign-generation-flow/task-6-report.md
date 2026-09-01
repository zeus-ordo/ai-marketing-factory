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
