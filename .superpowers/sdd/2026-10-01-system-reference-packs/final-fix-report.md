# System Reference Packs Final Fix Report

Date: 2026-10-01

## Fixes

- `ContextSourceItem` removes `stored_path` from persisted/displayable metadata and retains it only as runtime transient state until image bytes are built.
- Generation-context persistence defensively strips `stored_path`; Context Viewer responses recursively remove the field from legacy records as well as binary payload fields.
- Pack missing-file audits now include `pack_name` and `source_type` with the existing Pack id, role, mode, reason, and priority provenance.
- The file-preview contract verifies Pack previews go through `FilePreviewModal` and `fetchCampaignContent`, with no protected `content_url` bound directly to an image element.

## Verification

- Campaign-service reference/context/image tests: 68 passed; one pre-existing environment-sensitive regeneration test requires the repository root on `PYTHONPATH` when invoked from the service directory.
- Context Viewer tests: 43 passed.
- Frontend file-preview contract: passed.
- Context Viewer production build: passed.
- Frontend production build: passed.

Builds emitted only existing Next.js workspace-root warnings about multiple lockfiles.

## P1 Cache-Loss Follow-Up

Commit `8984dd3` correctly removed local paths from persisted context metadata, but a restart then left hydrated `ContextSourceItem` instances without runtime attachment paths. The follow-up rehydrates paths only after a persistence cache miss by matching each persisted item by `source_type` and `source_id` against current campaign references and active Pack items. The rehydrated path is stored only in the runtime-only field and is never written to `metadata_json` or returned by the Context Viewer.

The regression persists a sanitized context, clears the in-memory caches, loads it through `snapshot_for_campaign`, and verifies image bytes are attached again while `stored_path` remains absent from item metadata.

## Compatibility And Privacy

Selection ordering and Pack limits remain unchanged. Runtime attachment still reads the transient path before it is discarded from persistence. No image bytes or local filesystem paths are included in generation-context metadata or Context Viewer responses.

## Final Industry Knowledge Cache-Loss Fix

- Knowledge context normalization now accepts `stored_path` at either the row level or under `row["metadata"]`.
- Generation-context creation and cache-miss rehydration keep the path only in `ContextSourceItem.transient_stored_path`; persisted metadata and Context Viewer responses remain path-free.
- Added a restart/cache-loss regression for an industry-matched knowledge image and verified its image bytes are attached after rehydration.

## Final Verification

- Campaign-service suite: 198 passed, 2 skipped, 4 existing deprecation warnings.
