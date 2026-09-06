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
