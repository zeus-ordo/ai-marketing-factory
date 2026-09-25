# Reference Attachment Audit in Context Viewer

## Goal

Make it possible to verify from the Context Viewer that the selected Reference
image bytes were attached to an image-generation request, without exposing
base64 data or other secrets.

## Data flow

For image-generation payloads, persist a sanitized `reference_audit` object in
the existing LLM payload context metadata. The audit contains aggregate counts
and per-reference metadata only: reference ID, file name, MIME type, folder,
and SHA-256. The image bytes remain transient in the worker request and are
never stored in the viewer database.

The viewer detail query returns the audit from payload context metadata. Older
activities without this field remain supported and show an explicit
"Audit unavailable for this activity" state.

## Viewer behavior

The `References supplied` panel adds an audit summary:

- `Attached successfully` when selected and attached counts match and there
  are no failures.
- `Attachment incomplete/failed` when counts differ or failures exist.
- selected count, attached count, and multimodal status.
- a row for each attached Reference with ID, file name, MIME type, folder, and
  SHA-256.
- failure rows with Reference ID and failure category when present.

The panel must not render or download base64 image data. Existing text and JSON
download actions remain available for non-sensitive context metadata.

## Compatibility and error handling

- Missing or malformed audit metadata must not break activity detail loading.
- Non-image activities retain the current References supplied behavior.
- The audit is informational; generation already fails terminally when the
  campaign service cannot attach a selected Reference.

## Tests

- campaign-service test verifies the persisted payload context contains the
  sanitized audit and no image data.
- Context Viewer query test verifies audit metadata is selected from payload
  context.
- Context Viewer page test verifies success, failure, and legacy empty states.
