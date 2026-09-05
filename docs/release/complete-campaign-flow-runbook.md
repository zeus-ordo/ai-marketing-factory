# Complete Campaign Flow Runbook

## Configuration

Use `EXTERNAL_SEARCH_PROVIDER=disabled` for local, offline, and privacy-sensitive
deployments. To enable the Google adapter, inject these values out of band:

```text
EXTERNAL_SEARCH_PROVIDER=google
EXTERNAL_SEARCH_API_KEY=<secret-manager-reference>
EXTERNAL_SEARCH_ENGINE_ID=<engine-id>
```

The API key must exist only in the runtime secret store or VM secret file. It
must not appear in Git, database rows, prompts, fixtures, ordinary logs, or
test output. Search failure is non-fatal: the run continues with internal-only
context and records a sanitized status (`not_configured`, `quota`, `timeout`,
or `provider_error`). `not_configured` is expected when search is disabled or
Google credentials are incomplete; it is not a worker failure.

For local compose use, create an ignored `deploy/local-secrets.override.yml` or
the ignored root `.env.local` and provide `POSTGRES_PASSWORD` and
`MEMBERSHIP_DB_PASSWORD` there. Verify the file is ignored with
`git check-ignore deploy/local-secrets.override.yml`; never add it to Git. The
campaign-service `start-backend.bat` likewise requires
`CHATBOT_INTERNAL_API_KEY` and `CHAT_AUDIT_API_KEY` to already exist in the
shell environment and exits without printing their values when either is
missing.

## API and Data Contract

- `POST /api/v1/campaigns` returns `422` for blank required fields and for
  `deliverables.ads_strategy > 0` with a non-positive/non-finite budget.
- `POST /api/v1/campaigns/{campaign_id}/run` creates one immutable context
  snapshot for the run before dispatch.
- Campaign and review responses may include `generation_context_id`,
  `source_summary`, task status/error/retry fields, provider, and model. These
  fields are additive; existing clients may ignore them.
- `GET /api/v1/review/items?run_id=<run>` returns diagnostics for that run only.
- A worker result with no displayable output is `failed`, never `passed`.

## Operations

1. Check `/health`, queue overview, consumer groups, and recent audit events.
2. For a failed dependency, expect descendants to become `blocked` while
   unrelated tasks continue.
3. Campaign-service worker HTTP dispatch retries are bounded by
   `WORKER_RETRY_MAX_ATTEMPTS` (default `2`) and use
   `WORKER_RETRY_BACKOFF_SECONDS` as the local retry wait setting. The
   orchestrator has a separate hardcoded `MAX_RETRY = 2` in
   `services/orchestrator/app/main.py`; its exponential delay is capped at 300
   seconds. These limits are separate and both are finite.
4. Use the single-task retry endpoint for operator retry. It is bounded by
   `MANUAL_RETRY_MAX_ATTEMPTS` (default `3`) and does not change the
   orchestrator's automatic `MAX_RETRY`.
5. If a retry dispatch fails, verify reconciliation changed the task to a
   terminal retryable state. A zero-row reconciliation is `recovery_pending`,
   not success.
6. After restart, verify pending-message reclamation and cold-cache context
   hydration before replaying work.

Alert on retry exhaustion, blocked-task growth, DLQ growth, persistence or
reconciliation errors, missing context hydration, and external-search failure
rate. Alert payloads must contain IDs and sanitized classifications, never
tokens, API keys, authorization headers, or raw provider responses.

## Migrations

Run campaign-service initialization/migrations as an additive step before the
new application image receives traffic. Preserve existing campaign/reference
data. Back up PostgreSQL and Redis first, and verify the generation-context and
task-attempt structures after migration. No destructive migration is part of
this flow.

## Verification Commands

```bash
python -m pytest tests_e2e/test_complete_campaign_flow.py -q
python -m pytest tests_e2e/test_permissions_and_folder_scope.py -q
python -m pytest -m e2e --collect-only
pytest services/campaign_service -q
pytest services/orchestrator -q
npm run check:api:regression
npm run lint
npm run build
```

The deterministic suite uses ASGI TestClient plus mocked provider/worker/storage
boundaries and is safe without external credentials. It is not a localhost
smoke test. Live E2E tests are separately marked and require explicit
`RUN_LIVE_E2E=1`, running services, and test accounts described in
`tests_e2e/conftest.py`.

`npm run check:api:regression` is a live-service check, not an offline test. It
must be run only with the frontend/API stack available; when services are not
running it fails with an unavailable fetch and must be reported as such, never
treated as a pass.

## Permissions and Folder Rollout

Run the permissions/folder E2E gate with mocked providers and test identities.
It verifies Manager review access, company-admin same-company role assignment,
platform-folder read/use-only behavior for company users, platform-admin
folder mutation, company isolation, and association reads after a persistence
reload. The additive migration must be applied and existing folder/reference
counts checked before traffic is moved.

Keep `lib/server/folders-store.ts` and local folder directories in place until
backend persistence and read verification have passed. Only then can local
folder-store deprecation be considered, and the decision must be recorded in
the rollout report.
