# Task 5 Report

## Status

Implemented Task 5 only. Text generation now receives structured enriched attributes and provenance without image parts. Image generation preserves mandatory Pack/manual precedence, adds at most three enriched visual anchors within the six-image cap, and sends attributes separately as worker text context. Audit and worker contracts reject private paths and do not persist image bytes.

## Changed Files

- `services/campaign_service/app/context_assembler.py`
- `services/campaign_service/app/main.py`
- `services/campaign_service/test_image_generation_contract.py`
- `services/campaign_service/test_llm_context_capture.py`
- `services/worker_image/app/main.py`
- `services/worker_image/app/schemas.py`
- `services/worker_image/test_prompt.py`
- `services/worker_image/test_reference_images.py`

## Test Summary

- `python -m pytest services/campaign_service/test_image_rag_retrieval.py services/campaign_service/test_context_assembler.py -q`: PASS, 37 passed, 2 existing FastAPI deprecation warnings.
- `python -m pytest test_image_generation_contract.py test_llm_context_capture.py -q` from `services/campaign_service`: PASS, 28 passed, 1 skipped, 2 existing FastAPI deprecation warnings.
- `python -m pytest test_reference_images.py test_prompt.py -q` from `services/worker_image`: PASS, 8 passed.
- `python -m compileall -q services`: PASS.
- `git diff --check`: PASS.

## Final Role Audit Remediation

- Added enriched `role` to the sanitized audit-reference projection in `services/campaign_service/app/main.py`.
- Added a generation-contract regression asserting enriched audit references retain `role`.

## Final Verification

- `python -m pytest test_image_generation_contract.py test_llm_context_capture.py -q`: PASS, 30 passed, 1 skipped, 2 existing FastAPI deprecation warnings.
- `python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_image_rag_retrieval.py -q`: PASS, 37 passed, 2 existing FastAPI deprecation warnings.
- `python -m pytest test_reference_images.py test_prompt.py -q`: PASS, 10 passed.
- `python -m compileall -q services`: PASS.
- `git diff --check`: PASS.

## Commit

- `feat: send attributes and bounded visual anchors`

## Concerns

- Existing pytest-asyncio and FastAPI deprecation warnings remain.
- The pre-existing context-assembler import-path collision occurs when that test is run from the campaign-service directory; the required Task 4 command from the repository root passes.
- Pre-existing untracked plan files were not staged or modified.

## Findings Remediation

- Reused the Task 1 strict safe-attributes validator plus JSON serialization before generation payload attributes; nested private paths, binary fields, and base64 data are rejected from the payload.
- Added role to enriched-anchor provenance and fixed candidate/attribute/anchor/attachment audit counts, including zero-candidate audits.
- Configured `ReferenceImage` with `extra="forbid"` and made worker unsafe-field/value checks recursive across attributes, anchors, and audit payloads.
- Added regression coverage for nested unsafe attributes, zero counts, anchor role provenance, nested unsafe audit data, and image-part `stored_path` extras.

## Remediation Verification

- `python -m pytest test_image_generation_contract.py test_llm_context_capture.py -q`: PASS, 30 passed, 1 skipped, 2 existing FastAPI deprecation warnings.
- `python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_image_rag_retrieval.py -q`: PASS, 37 passed, 2 existing FastAPI deprecation warnings.
- `python -m pytest test_reference_images.py test_prompt.py -q`: PASS, 10 passed.
- `python -m compileall -q services`: PASS.
- `git diff --check`: PASS.
