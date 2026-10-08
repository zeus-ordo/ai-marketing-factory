# Image Generation and Batch Upload Hardening

**Date:** 2026-09-06  
**Status:** Approved design; implementation not started

## Problem Statement

Two production-facing risks require hardening:

1. Image generation can surface as HTTP 502 when the provider returns an
   unexpected response shape, an upstream error, or no usable image data. A
   provider response with no image may also be treated as success or replaced
   with a fallback SVG, obscuring the failure.
2. Batch uploads use concurrent per-file requests, but the frontend ignores
   rejected `Promise.allSettled()` results and can start a campaign after a
   partial upload failure.

The GCP logs checked during design did not contain recent image 502, empty
image, upload 413, or upload 502 matches. The code paths and missing tests
still make both behaviors reproducible risks that need deterministic handling.

## Goals

- Treat a real-provider response without a usable image as failure.
- Retry only transient image-provider failures with bounded exponential backoff.
- Preserve sanitized, actionable provider failure metadata without secrets.
- Prevent a campaign from starting when any selected upload failed or remains
  incomplete.
- Surface per-file upload state and allow retry/remove of failed files.
- Enforce upload authorization and validation at the backend as well as the UI.
- Add focused regression, service, and E2E coverage before rollout.

## Non-goals

- Replacing the current upload flow with an asynchronous upload-session system.
- Replacing all providers or redesigning the orchestrator/DLQ architecture.
- Removing the local folder/upload store before persistence and restart checks
  pass.
- Changing the selected policy: any failed batch file blocks campaign start.

## Design

### 1. Image generation contract

The flow remains:

```text
campaign-service -> worker-image -> provider adapter -> provider
                 <- validated image assets or typed failure
```

The worker-image provider adapter will:

- Parse and validate each provider response independently.
- Treat HTTP 200 with missing, empty, malformed, or unusable image data as a
  provider failure.
- Never substitute a fallback SVG for a real-provider success.
- Keep stub-mode output explicitly marked as `stub`; stub output must not be
  confused with strict real-mode output.

Failure classification:

| Condition | Behavior |
|---|---|
| HTTP 429 | Retry with exponential backoff and `Retry-After` when present |
| HTTP 500/502/503/504 | Retry up to three attempts |
| Timeout/connection error | Retry up to three attempts |
| HTTP 400/401/403/404 | Fail immediately |
| HTTP 200 with no usable image | Retry as transient provider failure |
| Exhausted retry or non-retryable error | Fail task and use existing orchestrator/DLQ flow |

Typed failure metadata may include provider, model, status code, retryable
flag, attempt count, and a sanitized message. API keys, complete upstream
responses, and secret-bearing prompts must not be logged or persisted.

Campaign-service must only persist/report successful image generation when at
least one validated image asset exists. An empty asset list is a task failure,
not `assets_saved: 0` success.

### 2. Batch upload contract

The existing per-file upload API remains the transport boundary. The frontend
will add:

- Preflight count, byte-size, extension, and MIME validation.
- Bounded upload concurrency.
- Per-file state: `pending`, `uploading`, `success`, or `failed`.
- Per-file retry and remove actions.
- A campaign-start guard: any `failed` or `uploading` file disables Start.
- Already successful files are not uploaded again during retry.

The backend will independently enforce:

- Campaign ownership/company access before accepting a reference upload.
- Existing file size and extension/type rules, with stable error codes.
- Safe persistence behavior and metadata/file consistency.

Stable error codes include `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`,
`CAMPAIGN_ACCESS_DENIED`, `UPLOAD_TIMEOUT`, and `PERSISTENCE_ERROR`.

The batch result model is per-file and must preserve successful results while
surfacing failures:

```text
{
  file,
  status: success | failed,
  reference_id?,
  error_code?,
  message?
}
```

### 3. Testing and rollout

Image adapter tests will cover valid responses, alternate/invalid shapes,
empty results, provider 429/5xx/timeout, non-retryable 4xx, retry count,
backoff, and sanitized errors. Campaign-service tests will cover empty asset
rejection and failure trace persistence.

Upload backend tests will cover same-company success, cross-company denial,
size/type rejection, persistence failure, and partial batches. Frontend tests
will cover preflight validation, bounded concurrency, failure surfacing,
start blocking, retry-only-failed behavior, and all-success start enablement.

E2E acceptance will cover:

1. A valid multi-file batch.
2. One oversized file blocking campaign start.
3. One invalid file blocking campaign start while valid files remain visible.
4. Retrying the failed file and starting only after all files succeed.
5. Image generation with a controlled provider response and validated asset.
6. Restart persistence for uploaded files and metadata.

Rollout sequence:

1. Run focused tests, service regressions, lint, and build.
2. Deploy to staging/GCP.
3. Run a controlled image smoke test reporting only provider, status, and asset
   count.
4. Run 1-, 2-, and 10-file upload batches, including an intentional failure.
5. Compare database metadata and filesystem objects.
6. Restart the relevant service and verify assets remain readable.
7. Observe image 502/empty-result and upload-failure metrics before wider use.

## Operational Safety

- Create a Cloud SQL backup before any production schema or persistence change.
- Do not print or modify provider keys, JWT secrets, or environment files.
- Preserve the local folder/upload store until backend persistence and restart
  verification are complete.
- Existing known full-suite test limitations must remain explicitly reported,
  not hidden by narrowing the test command.

## Success Criteria

- A real-provider empty image can never be reported as successful generation.
- Transient image provider failures retry within bounded limits and produce a
  typed failure after exhaustion.
- Any failed batch upload blocks campaign start and identifies the failed file.
- Failed files can be retried without duplicating successful uploads.
- Cross-company uploads are rejected.
- Focused and E2E tests demonstrate these rules, and GCP smoke/restart checks
  pass before the change is considered production-ready.
