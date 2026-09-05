# Task 4 Report

## Changed Files

- `tests_e2e/test_permissions_and_folder_scope.py`
- `docs/release/deployment-checklist.md`
- `docs/release/complete-campaign-flow-runbook.md`
- `task-4-report.md`

The pre-existing changes in `deploy/docker-compose.yml`,
`services/campaign_service/test_industry_matching.py`, and
`services/worker_copy/app/main.py` were not modified.

## Test Summary

- `python -m pytest tests_e2e/test_permissions_and_folder_scope.py -q`: PASS, 3 passed, 2 existing FastAPI deprecation warnings.
- `python -m pytest tests_e2e/test_complete_campaign_flow.py -q`: PASS, 11 passed, 2 existing deprecation warnings.
- `python -m pytest tests_e2e/test_permissions_and_folder_scope.py tests_e2e/test_complete_campaign_flow.py -q`: PASS, 14 passed, 2 existing deprecation warnings.
- `python -m pytest services/membership_service -q`: PASS, 18 passed.
- `python -m pytest services/orchestrator -q`: PASS, 25 passed, 2 existing deprecation warnings.
- `python -m pytest services/campaign_service -q`: LIMITATION, 118 passed, 1 skipped, 1 failed. Existing `test_invalid_campaign_is_not_persisted` calls `create_campaign` without the required JWT header and receives 401 before its expected 422 validation.
- `python -m pytest services/membership_service services/campaign_service -q`: LIMITATION, collection fails because both services use the top-level Python package name `app`; run the service suites in separate processes.
- `python -m compileall -q services`: PASS.
- `node scripts/check-secrets.mjs`: FAIL on existing local/test environment values (weak/default secret names reported only); no secret values were printed or changed.
- `npm run check:api:regression`: PASS, all listed checks passed.
- `npm run lint`: PASS, 0 errors and 12 existing warnings.
- `npm run build`: PASS, production build and TypeScript completed; Next.js reported the existing multiple-lockfile workspace-root warning.
- `git diff --check`: PASS.

The new offline E2E uses mocked/in-memory boundaries and no provider keys,
JWTs, localhost probes, or live identities. It covers Manager review access,
platform folder read/use-only behavior, platform-admin mutation, company folder
isolation, same-company role assignment with platform-role rejection, and
association reads after replacing the persistence object.

## Backup

- Project: `market-factory`
- Cloud SQL instance: `ai-marketing-postgres`
- Backup ID: `1788626975891`
- Status: `SUCCESSFUL`
- Description: `task-4-permissions-folder-scope-pre-deploy-2026-09-06`
- Created before the deployment attempt. No production schema mutation was
  performed.

## Deployment

- Target revision: `6c1e01dd3f924765307810b346ee9fb0332d5f05`
- Status: NOT DEPLOYED. The VM repository did not contain the target revision;
  checkout returned `fatal: reference is not a tree`.
- Existing VM revision: `d20eaddc4af26adfe0f018b23d1860227710fc51`.
- Existing Compose services: all listed services reported `running`.
- No fallback deployment of the older `origin/master` revision was performed.
- Migration/init for the target revision was not run because its revision was
  unavailable. No schema mutation was made.

## Post-Deploy Checks

- VM `ai-marketing-factory` in `asia-east1-a`: `RUNNING`.
- Cloud SQL `ai-marketing-postgres`: `RUNNABLE`.
- Redis `ai-marketing-redis`: `READY`.
- VM `http://localhost/`: `307`.
- VM `http://localhost:8095/health`: `200`.
- VM `http://localhost:8080/health`: `000`, connection refused.
- `/var/lib/ai-marketing-factory/campaign_references`: present.
- `/var/lib/ai-marketing-factory/generated_assets`: present.
- Target-revision smoke flow, account-separated production checks, and
  association verification against the deployed target: NOT RUN because the
  target revision was unavailable.

## Concerns and Limitations

- The target commit is not available from the VM's configured Git remotes;
  publishing or changing remotes was not authorized.
- The campaign-service suite has the documented pre-existing auth/validation
  mismatch; the deterministic offline gates pass.
- Existing pytest/FastAPI deprecation warnings and lint warnings remain.
- The repository secret gate cannot pass against the existing local/test env files; those files were not modified.
- The combined membership/campaign pytest command has a pre-existing `app` module collision; separate service commands pass as documented.
- Local folder storage was preserved. Backend persistence/read verification is
  covered offline, but production restart verification has not completed, so
  local-store deprecation/removal is not safe to recommend.
