# Multimodal Reference Image Design

## Goal

Ensure image generation uses the actual selected Reference images, not only their filenames or text labels, and never reports a successful image generation when the selected references failed to reach the image model.

## Product Decisions

- Select Reference images with deterministic rules; do not call another LLM or embedding model.
- Select at most 6 images per image-generation task:
  - up to 4 manually uploaded or campaign-selected references;
  - up to 2 images from matching knowledge folders.
- Preserve stable ordering so the same campaign state produces the same selected set.
- Manual campaign references have priority over industry-matched folder references.
- If any selected Reference cannot be read, validated, or attached to the provider request, block image generation and report the failure.

## Data Flow

1. Campaign-service resolves selected campaign references and matching folder items.
2. The deterministic selector filters image MIME types, verifies file existence, applies size/dimension limits, and returns up to 6 references.
3. Campaign-service converts selected files into provider-ready image parts or a secure internal attachment representation.
4. The image worker accepts `reference_images` in addition to the text prompt, sizes, and style profile.
5. The Gemini provider request includes the prompt plus actual image parts.
6. The worker returns attachment counts and failed reference IDs; a non-empty failure list is terminal for that image task.

## Provider Semantics

- References are labeled as visual style/content references.
- The prompt must instruct the provider to use references for composition, color, layout, brand/product appearance, and visual direction rather than blindly copying text or assets.
- Prompt-only generation is not an acceptable fallback when selected images fail.

## Audit Record

Persist or expose for each image-generation attempt:

- selected Reference IDs and filenames;
- folder and source type;
- MIME type, byte size, and content hash;
- selected image count;
- successfully attached image count;
- failed image IDs and error categories;
- provider/model and whether the request was multimodal.

Do not log image bytes, credentials, signed URLs, or other secrets.

## Acceptance Criteria

1. An image task with valid selected references sends actual image parts to the worker/provider.
2. The activity log proves which references were selected and attached.
3. An unreadable or oversized selected image blocks image generation with a clear error.
4. A campaign with no valid image references can still use the existing prompt-only path only when no references were selected.
5. Copywriting and other task types remain unchanged.
6. Existing image provider contract tests, campaign-service tests, and worker-image tests pass.
