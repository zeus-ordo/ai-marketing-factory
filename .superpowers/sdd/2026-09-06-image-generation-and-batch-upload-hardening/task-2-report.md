# Task 2 Report

## Changed Files

- `services/campaign_service/app/main.py`
  - Validate base64 image data URLs at the campaign boundary.
  - Treat image cache failures and zero valid image assets as failed results.
  - Record only sanitized retry metadata in worker dispatch traces; omit worker payload prompts.
- `services/campaign_service/test_image_generation_contract.py`
  - Added the four required image-generation contract tests.
- `.superpowers/sdd/2026-09-06-image-generation-and-batch-upload-hardening/task-2-report.md`
  - Added this report.

## TDD Evidence

### Red

Command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Result: `3 failed, 1 passed, 2 warnings in 0.72s`.

Failures demonstrated the missing production behavior: empty and malformed image results returned `accepted`, and retry traces did not contain the required sanitized retry metadata.

### Green

Command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Result: `4 passed, 2 warnings in 0.72s`.

Command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_task6_routes.py -q
```

Result: `26 passed, 2 warnings in 0.76s`.

## Concerns

- Pytest reports two existing deprecation warnings from `pytest-asyncio` configuration and FastAPI `on_event` usage.
- Verification covered the mandated contract and route suites, not the entire repository test suite.

## Review Fix Report

### Fixes

- Cache/download failures now discard the candidate image and return a failed zero-count result; the original provider URL is never persisted.
- Image data URLs now require one of the Task 1 supported image MIME types, a `;base64` marker, strict base64 decoding, and non-empty decoded bytes.
- Worker failure traces now contain only bounded task, provider, status, retry, attempt, error-code, and fixed safe-message fields. Raw provider errors, prompts, and worker URLs are excluded.
- Non-strict generation now raises on zero displayable assets, preventing zero-asset success traces.
- Added regressions for cache failure, arbitrary non-base64 data URLs, sanitized traces, non-strict empty results, and actual local-file download/cache persistence.

### Review-Fix TDD Evidence

Red command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Result: `5 failed, 3 passed, 2 warnings in 0.75s`.

The failures covered cache failure persistence, arbitrary data URL acceptance, trace fields, non-strict empty generation, and actual file-cache metadata.

Green command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_worker_result_state.py services/campaign_service/test_task6_routes.py -q
```

Result: `46 passed, 2 warnings in 0.83s`.

Additional trace-boundary TDD red command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Result: `1 failed, 8 passed, 2 warnings in 0.75s` because the new bounded trace helper did not yet exist.

Final green command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_worker_result_state.py services/campaign_service/test_task6_routes.py -q
```

Result: `47 passed, 2 warnings in 0.78s`.

The standalone final contract run also passed: `9 passed, 2 warnings in 0.72s`.

### Review-Fix Concerns

- The same two existing deprecation warnings remain: unset `pytest-asyncio` loop scope and FastAPI `on_event`.
- Focused suites passed; the full repository suite was not run.

## Re-Review Fix Report

### Fixes

- Restored `error`, `error_detail`, and `worker_url` in worker failure traces with fixed safe messages and null URL values.
- Normalized provider labels through the Task 1 allowlist (`gemini`, `minimax`, `stability`), using `unknown` for hostile or unsupported values.
- Made data URL base64 detection case-insensitive and verified actual decoded image bytes are written to the generated cache.
- Added regression coverage for trace-schema compatibility, hostile providers, uppercase base64 markers, valid PNG bytes, and existing retry/DLQ-compatible metadata.

### TDD Evidence

Red command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py -q
```

Result: `3 failed, 8 passed, 2 warnings`.

The failures covered missing compatible trace fields, unnormalized hostile providers, and uppercase base64 being cached as literal text.

Green command:

```text
python -m pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_worker_result_state.py services/campaign_service/test_task6_routes.py -q
```

Result: `49 passed, 2 warnings in 0.79s`.

### Concerns

- Existing pytest-asyncio and FastAPI deprecation warnings remain.
- The full repository suite was not run.
