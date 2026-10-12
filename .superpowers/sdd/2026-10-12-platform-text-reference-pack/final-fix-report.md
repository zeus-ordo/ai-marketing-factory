# Final Fix Report

Date: 2026-10-12

## Findings Addressed

1. Shared upload preflight now matches the backend text contract. `.txt` accepts `text/plain` and octet-stream; `.md` accepts `text/markdown` and octet-stream. Image MIME validation remains policy-specific and strict. Backend policy constants and contract coverage were updated for both text extensions.
2. Image-generation worker prompts no longer receive snapshot text context. Image payloads also omit structured platform text references, while `context_sources` continues to preserve text for provenance and textual RAG/context payloads retain their references.
3. Persistent Reference Pack item deletion reads the stored path before the soft delete and removes the uploaded file only after successful database deletion. The in-memory behavior remains unchanged.

## Verification

- `python -m pytest services/campaign_service/test_batch_upload.py services/campaign_service/test_reference_pack_text.py services/campaign_service/test_reference_packs.py services/campaign_service/test_image_generation_contract.py -q`: 80 passed.
- `python -m pytest services/campaign_service/test_context_assembler.py::test_asset_regeneration_sends_complete_v2_image_payload_and_sanitizes_audit -q`: 1 passed.
- `node scripts/check-reference-pack-form-contract.mjs`: passed.
- `npm run build`: passed.
- `git diff --check`: passed.

The combined focused command including `test_context_assembler.py` once reported one existing regeneration-test JWT failure; rerunning that test in isolation passed. The changed-area suite and the isolated regression both pass. Pytest emits the repository's existing FastAPI/pytest-asyncio deprecation warnings.

## Scope

Only the upload contract, image context separation, persistent deletion cleanup, and their regression/contract tests were changed. Unrelated pre-existing generated and worktree files were not staged.
