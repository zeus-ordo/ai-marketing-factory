# Image Generation and Batch Upload Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real image generation fail safely on empty/provider errors and prevent campaigns from starting after any failed batch upload.

**Architecture:** Keep the existing worker-image and per-file upload APIs, but enforce typed validation at provider/backend boundaries and explicit per-file state in the frontend. Image retries remain inside the provider adapter; upload retries remain per file in the UI. Existing orchestrator/DLQ handling remains the terminal task-failure mechanism.

**Tech Stack:** FastAPI/Python, httpx, pytest/pytest-asyncio, Next.js 16, TypeScript, Node contract tests, Docker Compose, GCP Compute Engine and Cloud SQL.

## Global Constraints

- A real-provider response without usable image data is always failure; never report it as success or replace it with fallback SVG.
- Retry HTTP 429, 500, 502, 503, 504, timeouts, connection errors, and empty/invalid image responses; retry at most three attempts with bounded exponential backoff and `Retry-After` support.
- Fail HTTP 400, 401, 403, and 404 without retry.
- Do not log or persist API keys, JWTs, complete upstream responses, or secret-bearing prompts.
- A campaign cannot start while any selected upload is `failed` or `uploading`.
- Successful uploads are not repeated when retrying failed files.
- Backend authorization and file validation are mandatory even when frontend preflight rejects the file.
- Preserve stub mode as explicitly marked `stub`; do not confuse it with strict real-mode success.
- Preserve existing orchestrator retry/DLQ behavior and local upload/folder storage until restart verification passes.
- Create a Cloud SQL backup before any production persistence/schema change.
- Existing full-suite limitations must be reported explicitly rather than hidden by narrowing test commands.

---

### Task 1: Harden worker-image provider adapters

**Files:**
- Modify: `services/worker_image/app/main.py:130-187,255-359`
- Test: `services/worker_image/test_provider_contract.py` (create)
- Test: `services/worker_image/test_prompt.py`

**Interfaces:**
- Preserve `POST /internal/workers/image/run` and `ImageRunResponse`.
- Add an internal provider result/error contract used by `_generate_image_asset_url()` and `_generate_gemini_image()`/other provider adapters.
- A successful real-mode response must contain at least one validated `ImageAsset` with non-empty data/URL.

- [ ] **Step 1: Write failing adapter tests.**

Add mocked-`httpx.Client` tests named
`test_gemini_valid_image_response_returns_data_url`,
`test_gemini_empty_steps_raises_retryable_provider_error`,
`test_gemini_alternate_content_shape_is_rejected_without_secret_logging`,
`test_provider_429_retries_and_honors_retry_after`,
`test_provider_500_retries_three_times_then_fails`,
`test_provider_400_does_not_retry`, and
`test_run_endpoint_never_returns_success_with_empty_real_assets`.

The first test asserts a non-empty `data:image` base64 result. The empty and
alternate-shape tests assert a retryable typed failure. The 429/500 tests assert
the exact attempt count and bounded delay; the 400 test asserts one request.
The endpoint test asserts non-success for an empty real-provider result.

The tests must assert status classification, attempt count, and that exception
messages do not contain the fake API key or full provider body.

- [ ] **Step 2: Run tests to verify the contract fails.**

Run:

```bash
python -m pytest services/worker_image/test_provider_contract.py -q
```

Expected: failures for retry classification, empty response handling, and the
current fallback-SVG behavior.

- [ ] **Step 3: Implement the minimal provider error and retry contract.**

Implement a private typed error carrying `provider`, `status_code`,
`retryable`, `attempts`, and a sanitized message. Wrap provider requests in a
bounded retry helper:

```python
def _request_with_retry(request_fn, *, provider: str, max_attempts: int = 3):
    # retry 429/5xx/timeout/connection and empty-result validation failures;
    # use Retry-After when parseable, otherwise bounded exponential delay.
```

Do not include response bodies or credentials in the error. Keep provider
specific response parsing inside each adapter.

- [ ] **Step 4: Remove real-mode empty-result fallback.**

Change the real-mode loop so an empty `generated_url` raises the typed failure
instead of calling `_fallback_svg_data_url`. Keep fallback SVG only in the
explicit non-strict stub branch and retain `provider`/`model_name` stub labels.

- [ ] **Step 5: Run focused tests and compile.**

Run:

```bash
python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py -q
python -m compileall -q services/worker_image
```

Expected: all focused tests pass; no API keys or provider bodies appear in
test output.

- [ ] **Step 6: Commit.**

```bash
git add services/worker_image/app/main.py services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py
git commit -m "Harden image provider failures and retries"
```

---

### Task 2: Reject empty image results in campaign-service

**Files:**
- Modify: `services/campaign_service/app/main.py:941-997,2361-2395,7291-7342`
- Test: `services/campaign_service/test_image_generation_contract.py` (create)
- Test: `services/campaign_service/test_task6_routes.py` if shared worker helpers are covered there

**Interfaces:**
- Preserve the current worker dispatch endpoint and task trace schema.
- `image_assets=[]` or an asset with missing/invalid URL is a failed generation
  result, never a successful persistence response.
- Preserve existing orchestrator retry/DLQ handoff and error classification.

- [ ] **Step 1: Write failing campaign-service tests.**

Add these tests with concrete assertions:

- `test_empty_image_assets_fail_generation_and_do_not_persist`: empty assets
  raise the task failure and leave no generated image row or file.
- `test_invalid_image_asset_url_fails_generation`: an asset with a missing or
  unsupported URL is rejected before download and persistence.
- `test_worker_502_records_retryable_failure_trace`: a worker 502 records the
  provider, status code, retryable flag, and attempt count without raw secrets.
- `test_successful_image_asset_persists_and_reports_positive_count`: one valid
  data URL is persisted and returns `assets_saved > 0`.

Assert no generated image row/file is created for empty or invalid results,
the failure trace includes sanitized status/provider/attempt metadata, and a
valid asset reports `assets_saved > 0`.

- [ ] **Step 2: Run the tests to verify they fail.**

```bash
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Expected: the current empty-result path either reports zero saved assets or
accepts an invalid asset instead of raising a task failure.

- [ ] **Step 3: Implement validation at the persistence boundary.**

Before download/cache/persistence, validate that the worker response contains
at least one usable asset and that each selected asset has a supported data URL
or fetchable URL. Raise the existing typed HTTP/task failure with sanitized
metadata when validation fails. Do not log the raw provider response.

- [ ] **Step 4: Verify retry/DLQ compatibility.**

Run the focused contract tests and existing campaign service tests in a fresh
process. Confirm the existing dispatch retry remains bounded and final failure
still reaches the orchestrator/DLQ path rather than being marked completed.

```bash
python -m pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_task6_routes.py -q
```

- [ ] **Step 5: Commit.**

```bash
git add services/campaign_service/app/main.py services/campaign_service/test_image_generation_contract.py services/campaign_service/test_task6_routes.py
git commit -m "Reject empty image generation results"
```

---

### Task 3: Harden backend batch upload authorization and validation

**Files:**
- Modify: `services/campaign_service/app/main.py:7010-7036,7090-7130,4963-4992,5125-5159`
- Modify: `services/campaign_service/app/persistence.py` only if upload metadata needs an additive status/error field
- Test: `services/campaign_service/test_batch_upload.py` (create)
- Test: `services/campaign_service/test_reference_scope.py`
- Test: `services/campaign_service/test_reference_folder_association.py` if folder-aware uploads are touched

**Interfaces:**
- Preserve `POST /api/v1/campaigns/{campaign_id}/references/upload`.
- Return stable error codes: `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`,
  `CAMPAIGN_ACCESS_DENIED`, `UPLOAD_TIMEOUT`, `PERSISTENCE_ERROR`.
- Return per-file-compatible status data without leaking local absolute paths
  or secrets.

- [ ] **Step 1: Write failing backend tests.**

Cover these tests with the stated assertions:

- `test_same_company_reference_upload_succeeds`: same-company JWT receives a
  reference ID and persisted metadata.
- `test_cross_company_reference_upload_is_forbidden_before_write`: the route
  returns 403 and neither bytes nor metadata are written.
- `test_oversized_upload_returns_file_too_large`: the route returns the stable
  `FILE_TOO_LARGE` code and leaves no partial file.
- `test_unsupported_extension_returns_unsupported_file_type`: the route returns
  `UNSUPPORTED_FILE_TYPE` and leaves no database row.
- `test_persistence_failure_returns_persistence_error_without_orphan_file`:
  persistence failure removes the temporary file and returns
  `PERSISTENCE_ERROR`.
- `test_upload_result_contains_reference_id_and_folder_id`: successful upload
  returns both identifiers without an absolute filesystem path.

Assert authorization happens before writing bytes, invalid files do not leave
filesystem or database orphans, and error responses contain no local path or
secret.

- [ ] **Step 2: Run tests to verify missing authorization/validation.**

```bash
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py -q
```

Expected: failures for cross-company upload authorization and stable batch
validation/error behavior.

- [ ] **Step 3: Add campaign access guard before file write.**

Use the existing campaign access/company authorization helper before reading the
upload body to disk. Reject cross-company or unauthenticated requests before
creating a file. Preserve internal/platform-admin bypass semantics only where
the existing API contract explicitly allows them.

- [ ] **Step 4: Normalize validation and cleanup.**

Validate extension, MIME, and size while streaming or immediately after the
bounded write. On any validation/persistence failure, remove the partial file
and avoid inserting an orphan row. Return the stable error code and sanitized
message. Apply equivalent limits to knowledge/manual asset upload paths or
explicitly route them through the same validator.

- [ ] **Step 5: Run focused backend tests and commit.**

```bash
python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py services/campaign_service/test_reference_folder_association.py -q
git add services/campaign_service/app/main.py services/campaign_service/app/persistence.py services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_scope.py services/campaign_service/test_reference_folder_association.py
git commit -m "Harden batch upload authorization and validation"
```

---

### Task 4: Implement frontend batch state and campaign-start gate

**Files:**
- Modify: `app/campaigns/page.tsx:595-605,1152-1157`
- Modify: `lib/api/campaigns.ts:425-482,1002-1016`
- Modify: `lib/i18n/translations.ts`
- Test: `scripts/test-batch-upload-contract.mjs` (create)
- Test: existing campaign frontend contract scripts as needed

**Interfaces:**
- Preserve `uploadCampaignReference` and existing upload endpoint signatures.
- Add a typed per-file result/state model used by the page:
  `pending | uploading | success | failed`.
- Keep `runCampaign` callable only after every selected file is `success`.

- [ ] **Step 1: Write failing frontend contract tests.**

The Node contract must contain these assertions:

- `preflight rejects invalid size/type before upload`: invalid files produce no
  network call and a stable client error.
- `upload concurrency is bounded`: the maximum active upload count never
  exceeds the configured limit.
- `partial failure blocks campaign start`: one failed result keeps Start
  disabled and renders the failed file.
- `retry only sends failed files`: retry invokes the API for failed files and
  does not repeat successful reference IDs.
- `all-success state enables campaign start`: Start becomes enabled only after
  every selected file has `success` state.

The test must detect that `Promise.allSettled` results are inspected rather
than ignored.

- [ ] **Step 2: Run the contract test to verify current behavior fails.**

```bash
node scripts/test-batch-upload-contract.mjs
```

Expected: failure because current code starts the campaign without inspecting
settled upload failures and has no per-file gate.

- [ ] **Step 3: Add shared client validation and typed upload results.**

In `lib/api/campaigns.ts`, add constants/helpers for allowed types, maximum
bytes, and bounded upload execution. Return sanitized `{ file, status,
reference_id?, error_code?, message? }` values instead of throwing away the
file identity.

- [ ] **Step 4: Add page state and failure gate.**

In `app/campaigns/page.tsx`, maintain per-file state, render upload progress and
localized error/retry/remove controls, and disable Start while any file is
`pending`, `uploading`, or `failed`. Retry only failed files. Keep successful
reference IDs and folder IDs unchanged.

- [ ] **Step 5: Add localized copy and run frontend checks.**

Add English, Traditional Chinese, and Japanese strings for invalid type/size,
uploading, retry, remove, partial failure, and blocked campaign start.

```bash
node scripts/test-batch-upload-contract.mjs
npm run lint
npm run build
```

- [ ] **Step 6: Commit.**

```bash
git add app/campaigns/page.tsx lib/api/campaigns.ts lib/i18n/translations.ts scripts/test-batch-upload-contract.mjs
git commit -m "Block campaigns after failed batch uploads"
```

---

### Task 5: Add E2E coverage and execute staged rollout

**Files:**
- Modify: `tests_e2e/test_permissions_and_folder_scope.py` only if shared fixtures are reusable
- Create: `tests_e2e/test_image_generation_and_batch_upload.py`
- Modify: `docs/release/deployment-checklist.md`
- Modify: `docs/release/complete-campaign-flow-runbook.md`
- Create: `docs/release/image-generation-and-batch-upload-runbook.md`

**Interfaces:**
- E2E uses mocked provider responses and deterministic test files offline.
- Production smoke uses a neutral prompt and reports only provider, HTTP status,
  attempt count, and asset count.

- [ ] **Step 1: Write failing E2E scenarios.**

Add deterministic tests named:

- `test_empty_real_image_response_fails_task`
- `test_valid_image_response_persists_asset`
- `test_partial_batch_failure_blocks_campaign_start`
- `test_failed_file_retry_then_all_success_allows_start`
- `test_restart_preserves_uploaded_file_and_metadata`

Each test must assert the externally visible result, not only an internal mock
call; the restart case must recreate the persistence/service object before
reading the file and metadata.

- [ ] **Step 2: Run E2E red and implement only fixture/test seams.**

```bash
python -m pytest tests_e2e/test_image_generation_and_batch_upload.py -q
```

Expected: failures until Tasks 1–4 contracts are integrated.

- [ ] **Step 3: Run the complete offline verification gate.**

```bash
python -m pytest tests_e2e/test_image_generation_and_batch_upload.py -q
python -m pytest services/worker_image -q
python -m pytest services/campaign_service -q
npm run lint
npm run build
git diff --check
```

Record existing campaign-service environment-ordering failures separately if
they remain; do not mark the gate fully green when they occur.

- [ ] **Step 4: Create backup and deploy staging/GCP.**

Before any production persistence change:

```bash
COMMIT="$(git rev-parse HEAD)"
gcloud sql backups create --project=market-factory --instance=ai-marketing-postgres --description="image-batch-pre-deploy-${COMMIT}"
gcloud sql backups list --project=market-factory --instance=ai-marketing-postgres --filter="description=image-batch-pre-deploy-${COMMIT}" --format="table(id,status,description)"
```

Deploy the approved commit through the existing `deploy/docker-compose.gcp.yml`
workflow. Do not print environment values or use an older revision.

- [ ] **Step 5: Run controlled post-deploy checks.**

Verify:

```bash
docker compose -f deploy/docker-compose.gcp.yml ps
curl -fsS http://127.0.0.1/
```

Run one neutral image request and report only status/provider/attempts/asset
count. Run 1-, 2-, and 10-file upload batches, including one intentional
failure; verify campaign start is blocked until retry succeeds. Compare DB
metadata and files, restart the relevant service, and verify assets remain
readable.

- [ ] **Step 6: Document and commit rollout evidence.**

Update the release checklist/runbook with exact test counts, backup ID,
deployed commit, health status, known limitations, and whether local storage
can be deprecated. Then commit:

```bash
git add tests_e2e docs/release
git commit -m "Verify image and batch upload rollout"
```
