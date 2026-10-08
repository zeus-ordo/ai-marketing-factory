# Task 1 Report

## Status

Implemented immutable/adjustable reference partition preservation for image regeneration.

- Added regeneration-safe snapshot metadata with stable selected IDs.
- Classified Brand Identity, Product, logo, real product, and protected references as `immutable`.
- Classified Style, Composition, Campaign Examples, and RAG anchors as `adjustable`.
- Rebuilt v2 image regeneration payloads with the reviewed snapshot's transient `reference_images` and sanitized `reference_audit`.
- Added explicit regeneration prompt rules that protect immutable references from user instructions.
- Kept provider APIs and existing payload fields unchanged.
- Audit metadata excludes transient bytes, base64, and private paths.

## TDD Evidence

Regression tests were added before implementation. The initial focused run failed because the regeneration metadata helper was absent and the old v2 regeneration path did not provide reference payload data. After implementation, the focused suite passed.

## Verification

- `python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py -q`: 53 passed, 2 pre-existing deprecation warnings.
- `python -m pytest test_reference_images.py test_provider_contract.py test_prompt.py -q` in `services/worker_image`: 36 passed.
- `npm test` in `context-viewer`: 45 passed.
- `npx tsc --noEmit`: passed.
- `npm run build`: passed.
- `git diff --check`: passed.

## Concerns

- Existing unrelated worktree changes (`next-env.d.ts`, `tsconfig.tsbuildinfo`, `artifacts/`, and existing documentation files) were not modified or staged.
- The worker provider API was intentionally not changed; regeneration fields remain additive to the campaign-service payload.

## Review Fixes

Applied the three Task 1 review findings:

- `_sanitize_persisted_context` now recursively removes reference-audit path fields, path-like values, bytes, data URIs, and base64/binary fields while retaining non-audit payload data.
- Regeneration accepts persisted selected IDs or partition metadata as the source of truth. It preserves their order and falls back to the existing deterministic selection only when persisted selection is absent. Non-image legacy IDs are ignored safely.
- The immutable-reference safeguard is repeated after the user regeneration instruction, so user text cannot override Brand Identity, Product, logo, real product appearance, or protected-reference constraints.

Added regression coverage for all three findings.

## Review Fix Verification

- `python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py -q`: 56 passed, 2 pre-existing deprecation warnings.
- `python -m pytest test_reference_images.py test_provider_contract.py test_prompt.py -q` in `services/worker_image`: 36 passed.
- `npm test` in `context-viewer`: 45 passed.
- `npx tsc --noEmit`: passed.
- `npm run build`: passed.
- `git diff --check`: passed.
