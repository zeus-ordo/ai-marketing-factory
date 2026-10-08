# Regeneration Reference Integrity Design

## Goal

Ensure v2 asset regeneration preserves the original campaign description and
reference images, especially immutable brand/product references such as logos
and real product images.

## Design

- Regeneration rehydrates the original generation snapshot by its reviewed
  `run_id`/`generation_context_id`.
- Image regeneration sends the original structured campaign brief,
  `reference_images`, and sanitized `reference_audit` again.
- Reference provenance classifies images as:
  - `immutable`: Brand Identity, Product, logo, real product, or explicitly
    protected user references.
  - `adjustable`: Style, Composition, Campaign Examples, and RAG visual
    anchors.
- The regeneration prompt explicitly requires immutable references to remain
  unchanged and permits user instructions to affect only adjustable references.
- Context Viewer receives the original activity description and v2 reference
  audit without image bytes, base64, or private paths.
- Existing API routes and provider contracts remain backward compatible.

## Verification

- Add regression tests proving v2 payload includes the original description,
  immutable references, adjustable references, and audit metadata.
- Verify Context Viewer sanitization retains description and provenance.
- Run campaign, worker-image, Context Viewer, frontend build, and production
  smoke checks.
