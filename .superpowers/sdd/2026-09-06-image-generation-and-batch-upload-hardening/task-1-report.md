# Task 1 Report

## Changed Files

- `services/worker_image/app/main.py`
  - Added typed, sanitized `ProviderError` metadata.
  - Added three-attempt bounded exponential retries for provider status failures, timeouts, connection errors, and invalid/empty image results.
  - Honors parseable numeric `Retry-After` values, capped by the retry delay bound.
  - Keeps 400, 401, 403, and 404 non-retryable.
  - Rejects empty real-provider assets in run and regenerate paths; fallback SVG remains limited to stub mode.
- `services/worker_image/test_provider_contract.py`
  - Added the seven required mocked-httpx provider contract tests.
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-1-report.md`
  - Added this report.

## TDD Evidence

### Red

After correcting the test-only context-manager fixture, before production changes:

```text
python -m pytest services/worker_image/test_provider_contract.py -q
7 failed, 0 passed
```

The failures were the expected missing `ProviderError`/retry contract and the existing endpoint behavior returning success for an empty real result. The initial collection attempt was blocked because the environment lacked the already-declared `prometheus-client` dependency; it was installed from `services/worker_image/requirements.txt` and the red command was rerun.

### Green

```text
python -m pytest services/worker_image/test_provider_contract.py -q
7 passed in 0.42s
```

```text
python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py -q
10 passed in 0.44s
```

## Verification

Exact commands run:

```bash
python -m pytest services/worker_image/test_provider_contract.py -q
python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py -q
python -m compileall -q services/worker_image
```

Compile result: exit code 0, no output or errors.

## Concerns

- Pytest emits the existing `pytest-asyncio` deprecation warning about an unset `asyncio_default_fixture_loop_scope`; it does not affect these synchronous tests.
- The focused verification does not exercise live provider APIs or the campaign-service persistence boundary covered by later tasks.
- `prometheus-client` was missing from the local Python environment and had to be installed from the existing worker requirements before tests could collect.

## Review Fixes

### Changed Files

- `services/worker_image/app/main.py`
  - Added structural validation for supported image MIME types, non-empty strict base64 data URLs, and HTTP(S) asset URLs.
  - Applied validation both inside provider adapters and at the real-mode endpoint boundary.
  - Hardened Stability, Gemini, and MiniMax response-shape parsing so malformed provider data becomes a typed sanitized retryable error.
  - Added standard HTTP-date parsing for `Retry-After`, retaining the existing bounded delay cap.
  - Removed raw unexpected exception text from endpoint error details.
- `services/worker_image/test_provider_contract.py`
  - Added regression tests for invalid data, MIME, and URL assets; malformed MiniMax responses; 401/403/404 classification; timeout/connection retries; HTTP-date retry hints; and sanitized endpoint errors.
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-1-report.md`
  - Appended this review-fix report.

### TDD Evidence

Red before the review-fix production changes:

```text
python -m pytest services/worker_image/test_provider_contract.py -q
4 failed, 15 passed
```

The failures covered invalid base64, unsupported MIME, malformed MiniMax URLs, and the unhandled malformed MiniMax response shape.

The endpoint-boundary validation was then added with a separate red-green cycle:

```text
python -m pytest services/worker_image/test_provider_contract.py -q
1 failed, 19 passed
```

The single failure was the new invalid real asset endpoint test, which passed after the boundary validator was implemented.

### Review-Fix Verification

Exact commands and results:

```bash
python -m pytest services/worker_image/test_provider_contract.py -q
20 passed in 0.44s

python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py -q
23 passed in 0.44s

python -m compileall -q services/worker_image
```

Compile result: exit code 0, no output or errors.

### Review-Fix Concerns

- Pytest continues to emit the existing `pytest-asyncio` deprecation warning about an unset `asyncio_default_fixture_loop_scope`.
- Retry-After HTTP-date tests use a current UTC date and verify the bounded delay; no live provider calls were made.
- Campaign-service persistence validation remains covered by the later task, not this worker-only change.

## Re-review Fixes

### Changes

- Clamped `_request_with_retry` caller overrides to the plan-mandated maximum of three attempts.
- Added coverage for future HTTP-date `Retry-After`, oversized numeric/date retry hints, and caller overrides above the attempt limit.
- Strengthened endpoint assertions for provider, status, retryability, attempts, sanitization, and absence of fallback SVG output for invalid real assets.
- Preserved provider validation, retry behavior, and explicit stub fallback behavior.

### TDD Evidence

Red before the production retry-limit change:

```text
python -m pytest services/worker_image/test_provider_contract.py -q
1 failed, 23 passed
```

The failure showed a caller-provided `max_attempts=10` produced 10 attempts instead of the required maximum of three.

Green after the fix:

```text
python -m pytest services/worker_image/test_provider_contract.py -q
24 passed in 0.44s
```

### Verification

Exact commands and results:

```bash
python -m pytest services/worker_image/test_provider_contract.py -q
24 passed in 0.44s

python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_prompt.py -q
27 passed in 0.45s

python -m compileall -q services/worker_image
```

Compile result: exit code 0, no output or errors.

### Concerns

- Pytest continues to emit the existing `pytest-asyncio` deprecation warning about an unset `asyncio_default_fixture_loop_scope`.
- Verification remains offline with mocked provider responses; no live provider calls were made.
