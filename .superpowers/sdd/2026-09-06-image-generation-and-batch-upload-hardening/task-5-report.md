# Task 5 Rollout Report

## Changed Files

- `tests_e2e/test_image_generation_and_batch_upload.py`
- `docs/release/deployment-checklist.md`
- `docs/release/complete-campaign-flow-runbook.md`
- `docs/release/image-generation-and-batch-upload-runbook.md`
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-5-report.md`

## Offline Commands And Results

- `python -m pytest tests_e2e/test_image_generation_and_batch_upload.py -q` -> `7 passed, 2 warnings` (1-, 2-, and 10-file deterministic batches included).
- `python -m pytest services/worker_image -q` -> `27 passed`.
- `python -m pytest services/campaign_service -q` -> `141 passed, 1 skipped, 2 failed`.
- `npm run lint` -> passed with 11 existing warnings, 0 errors.
- `npm run build` -> passed; Next.js production build completed.
- `git diff --check` -> passed with no whitespace errors.
- `python -m pytest -q` -> collection failed with 6 import errors from service-local `app` module collisions.

## Full-Suite Failures

- `services/campaign_service/test_campaign_validation.py::test_invalid_campaign_is_not_persisted` returned 401 instead of 422 because the test request did not satisfy the current internal-auth path.
- `services/campaign_service/test_context_assembler.py::test_review_regeneration_uses_snapshot_for_image_and_ads` attempted an unmocked `https://new` fetch and then had no saved asset.

These failures were reported separately and were not hidden by narrowing the commands.

The unscoped `python -m pytest -q` full-suite collection also failed because
service-local `app` modules collide when pytest is run from the repository
root. It reported six collection errors in orchestrator, worker-image, and
E2E modules, including `ModuleNotFoundError`/wrong-module imports. This is a
repository test-isolation limitation, not a passing full suite.

## Backup And Deployment

- Current approved branch commit observed before this task: `830a19530a63e96f70643631035d4ad641fef96c`.
- Backup verification command: `gcloud sql backups list --project=market-factory --instance=ai-marketing-postgres --limit=1 --format="table(id,status,description)"`.
- Latest existing backup observed: ID `1788632243840`, status `SUCCESSFUL`, description `permissions-folder-scope-pre-deploy-2026-09-06-fd3bfe6`.
- Task-specific backup: not created. No production persistence/schema change or production deployment was performed because the worktree contains an unrelated uncommitted `services/campaign_service/app/persistence.py` change and no safe approved deployment handoff was available.
- Deployed commit: not deployed.

## Local Health And Smoke

- `docker compose -f deploy/docker-compose.gcp.yml ps` -> all listed Compose services were `Up`; PostgreSQL and Redis were `healthy`.
- Campaign, decision, orchestrator, and worker-image `/health` requests -> `{"status":"ok"}`.
- `curl -fsS http://127.0.0.1/` -> public frontend response redirected unauthenticated traffic to `/dashboard`; no authenticated account smoke was run.
- Neutral live provider smoke: not run. No safe provider/account smoke credentials and approved neutral account were supplied; no provider result is claimed.
- 1-, 2-, and 10-file live upload batches: not run against production. Offline deterministic coverage verifies the failure/retry gate and restart readability.

## Limitations

Live GCP deployment, Cloud SQL task-specific backup creation, provider smoke, and authenticated upload batches remain pending an approved clean deployment commit and safe provider/account access. Local stores were preserved.
