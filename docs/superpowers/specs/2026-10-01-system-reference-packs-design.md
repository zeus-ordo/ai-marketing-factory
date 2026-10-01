# System Reference Packs Design

## Goal

Allow platform administrators to upload and manage system-level Reference
images in categorized Packs, then automatically include a bounded selection of
those images in every applicable campaign generation.

## Scope

The feature adds a platform-admin-only System Reference Packs area inside
Content Studio. It does not mix platform assets into company-owned Knowledge
items. Existing campaign References and company Knowledge remain supported.

Pack roles:

- `brand_identity`
- `product`
- `style`
- `composition`
- `campaign_examples`

Each Pack has an applicability scope, priority, selection mode, and image
limit. Applicability is either all campaigns or a normalized industry label.

## Data model

Add a `reference_packs` table with:

- `pack_id`
- `name`
- `role`
- `scope` (`platform`)
- `industry` nullable for global Packs
- `selection_mode` (`mandatory` or `optional`)
- `max_images`
- `priority`
- `is_active`
- `created_at`, `updated_at`

Link uploaded platform Knowledge items to Packs using a `reference_pack_id`
and keep the existing file storage and metadata. Pack membership must not
change company visibility rules; only platform administrators may create,
update, delete, or upload into platform Packs.

## Admin experience

Content Studio gets a `System Reference Packs` section visible only to platform
administrators. It supports:

- list and filter Packs by role, industry, and active status;
- create and edit Pack settings;
- upload multiple images into a Pack;
- preview and remove Pack images;
- show Pack image count and selection settings.

Non-platform users must not see the section or mutate platform Pack endpoints.

## Generation selection

At generation-context creation, assemble sources in this order:

1. active mandatory global Packs;
2. active mandatory industry Packs;
3. active optional industry Packs;
4. existing campaign References;
5. existing company Knowledge matches.

The image selector enforces a hard total of 6 images for the first version:

- mandatory `brand_identity`: up to 2;
- mandatory `product`: up to 2;
- optional `style`, `composition`, and `campaign_examples`: remaining slots;
- existing manual/campaign References retain priority over optional Pack items;
- industry/company matches fill only remaining slots.

When a Pack contains more images than its limit, selection is deterministic
but rotated by campaign/run identity so the same first files are not always
chosen. Duplicate files are removed by Reference ID and SHA-256. Missing files
are excluded and recorded as audit failures; mandatory Pack failures prevent
image generation rather than silently producing an unreferenced result.

The first version uses Pack metadata and deterministic rotation, not a new
vector database. A future retrieval layer can rank candidates within a Pack
without changing the Pack contract.

## Audit and persistence

The generation snapshot and payload audit identify each selected image with:

- `reference_id`
- `reference_pack_id`
- `pack_role`
- `selection_mode`
- `file_name`
- `mime_type`
- `folder`
- `sha256`
- selection reason and priority

Audit also records candidate count, selected count, attached count, failures,
and the selection policy version. Image bytes remain transient request data and
are never persisted in context metadata or exposed by Context Viewer.

## Error handling

- Non-platform users receive 403 for Pack management endpoints.
- Invalid role, scope, industry, MIME type, or Pack limits return 400.
- Missing files in optional Packs are recorded and skipped.
- Missing files in mandatory Packs fail image generation with a structured 422.
- Existing activities without Pack audit metadata remain readable.

## Testing

- API authorization and Pack CRUD/upload tests.
- Pack selection tests covering mandatory/optional priority, hard total of 6,
  deterministic rotation, duplicate removal, and missing mandatory files.
- Audit tests verify Pack metadata and selection reasons without image bytes.
- Context Viewer tests verify Pack information is rendered safely.
- Full campaign-service, frontend, worker-image, and Context Viewer suites.
