# Task 1 Report

## Status

Implemented the news release copy-length contract.

## Changes

- Updated campaign-service copy policy text to describe news releases as 1000-1400 characters.
- Updated campaign-service contract assembly to return 1000-1400 for news and press-release descriptions.
- Preserved social copy at 300-500 characters.
- Preserved ad/promotional copy at a maximum of 80 characters.
- Added worker-copy tests for inclusive 1000 and 1400 boundaries, rejection of 999 and 1401, prompt range propagation, and failure after two out-of-range repairs.
- Preserved the existing `invalid_copy_length` classification and two-repair limit.

## Tests

- `python -m pytest services/campaign_service/test_copy_length_contract.py -q`: passed.
- `python -m pytest services/worker_copy/test_copy_length.py -q`: passed.

## Concerns

- Pytest emits existing deprecation warnings for the unset `pytest-asyncio` fixture loop scope and FastAPI `on_event`; neither is related to Task 1.
- The combined campaign-service and worker-copy collection remains unsupported because of the pre-existing `app` module-path collision documented in `progress.md`.
