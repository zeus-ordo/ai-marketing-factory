# Task 1 Report: Copy Body Length Contract

## Status

Implemented Task 1 in `campaign-service`.

## Changes

- Added `get_copy_body_length_contract(campaign)` in `services/campaign_service/app/main.py`.
- Added deterministic mappings from the normalized project description:
  - Press-release terms (`公關稿`, `新聞稿`, `press release`, `public relations`) map to 300-500.
  - Social terms map to 100-200.
  - Promotional terms map to 0-100.
  - No explicit format maps to the backward-compatible 80-200 default.
- Added integer `body_min_length` and `body_max_length` fields to campaign-service copy payloads for:
  - Initial worker payload construction.
  - Initial worker dispatch.
  - Asset regeneration.
  - Review revision requests.
- Preserved existing payload fields and the natural-language Copy type policy.
- Added `services/campaign_service/test_copy_length_contract.py` with mapping and payload assertions.
- Did not modify `services/worker_copy`.

## Verification

- `python -m pytest -q services/campaign_service/test_copy_length_contract.py`
  - 10 passed, 2 existing deprecation warnings.
- `python -m pytest -q services/campaign_service/test_copy_length_contract.py services/campaign_service/test_task6_routes.py`
  - 32 passed, 2 existing deprecation warnings.

## Review

- Manual diff review completed.
- The independent reviewer dispatch failed at the tool layer and produced no review findings.
- Working-tree changes outside this task were left untouched: `.superpowers/sdd/` existing files and `docs/account-inventory.txt`.

## Concerns

- Pytest reports existing FastAPI and pytest-asyncio deprecation warnings; they are unrelated to this task.
- The brief does not enumerate every possible social or promotional synonym, so the helper uses the explicit required press terms plus common English/Chinese social and promotional terms covered by the new tests.
