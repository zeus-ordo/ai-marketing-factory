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
context and records a sanitized status (`quota`, `timeout`, or
`provider_error`).

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
3. Automatic retry is bounded by `WORKER_RETRY_MAX_ATTEMPTS`; backoff is capped
   by the orchestrator. Use the single-task retry endpoint for operator retry.
4. If a retry dispatch fails, verify reconciliation changed the task to a
   terminal retryable state. A zero-row reconciliation is `recovery_pending`,
   not success.
5. After restart, verify pending-message reclamation and cold-cache context
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
pytest tests_e2e/test_complete_campaign_flow.py -q
pytest services/campaign_service -q
pytest services/orchestrator -q
npm run check:api:regression
npm run lint
npm run build
```

The deterministic suite uses mocks/fixtures and is safe without external
credentials. Live E2E tests are separately marked and require the services and
test accounts described in `tests_e2e/conftest.py`.
