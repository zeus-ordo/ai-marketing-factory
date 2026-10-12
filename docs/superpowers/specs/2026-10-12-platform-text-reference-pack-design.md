# Platform Text Reference Pack Design

## Goal

Allow platform administrators to upload `.txt` and `.md` files into platform-level Reference Packs. These text references must be available to RAG and text context while preserving the existing image Reference Pack workflow.

## Scope

### In scope

- Platform-admin-only upload of UTF-8 `.txt` and `.md` files.
- Existing image formats remain supported without behavior changes.
- Existing Reference Pack metadata remains available: title, description, folder/category, and Pack role.
- Text references are persisted as platform knowledge items and are available to RAG/text context.
- Text references do not consume the fixed image quota and do not enter the image enrichment worker.
- API responses and audit metadata must not expose private storage paths, raw bytes, or base64 data.
- UI labels and validation must clearly identify supported image and text formats.

### Out of scope

- `.docx`, `.pdf`, `.rtf`, or other document formats.
- Converting text into images.
- New text-only Reference Pack APIs.
- Changes to user campaign-reference upload behavior.

## User Experience

The existing platform Reference Pack upload control will accept images and text files. It will communicate supported formats as `PNG/JPG/JPEG/WEBP/TXT/MD`. Text files will be represented by a text/file-type indicator rather than an image preview. Existing metadata fields and Pack role controls remain unchanged.

## API and Data Flow

The existing platform-admin Reference Pack item upload endpoint remains the single entry point. It will:

1. Authenticate and authorize the request as a platform administrator.
2. Validate extension and MIME type.
3. For images, preserve the current storage, public response, and image-enrichment behavior.
4. For `.txt` and `.md`, read UTF-8 text, persist the knowledge item and metadata, and skip image enrichment.
5. Mark text items with `file_type` `text/plain` or `text/markdown` and an analysis state that does not imply image analysis.
6. Return only sanitized public metadata.

Text content will flow through the existing knowledge/RAG context path. It will be treated as textual context and will not be included in image quota accounting or multimodal image partitions.

## Validation and Errors

- Accept `.txt` with `text/plain` and `.md` with `text/markdown` (allow compatible browser MIME variants when the extension is valid).
- Reject unsupported formats such as `.docx`, `.pdf`, and `.exe` with the existing unsupported-file error contract.
- Reject malformed or non-UTF-8 text with a clear client-safe validation error.
- Preserve the existing platform-admin `403` behavior for non-admin callers.
- Keep image upload validation and enrichment behavior unchanged.

## Testing

- Backend unit tests for successful `.txt` and `.md` uploads.
- Tests that text uploads skip image enrichment and persist correct metadata.
- Tests for unsupported formats, invalid MIME/extension combinations, and invalid UTF-8.
- Permission tests proving non-platform-admin callers cannot upload platform references.
- Sanitization tests proving responses omit private paths, bytes, and base64.
- Regression tests proving image upload still enqueues image enrichment.
- Frontend tests for accepted file types, visible format guidance, text-item rendering, and existing image behavior.
- Build, focused tests, and deployed smoke verification.

## Acceptance Criteria

1. A platform administrator can upload `.txt` and `.md` files to a platform Reference Pack using the existing UI.
2. Uploaded text appears as a platform knowledge/reference item with existing metadata fields.
3. Text is available to RAG/text context and is excluded from image quota and image enrichment.
4. Images continue to work as before.
5. Non-admin users and unsupported file types are rejected safely.
6. No private storage path or binary payload is exposed by the API or audit data.
