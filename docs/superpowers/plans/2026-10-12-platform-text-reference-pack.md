# Platform Text Reference Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow platform administrators to upload UTF-8 `.txt` and `.md` files into existing platform Reference Packs, make them available to textual RAG context, and keep image Reference Pack behavior unchanged.

**Architecture:** Extend the existing `/api/v1/reference-packs/{pack_id}/items/upload` multipart endpoint instead of adding a second API. The backend will branch after extension/MIME validation: images retain file storage and image enrichment; text files are stored as knowledge items without image analysis. The Content Studio upload control will accept both image and text files and render text items with file metadata rather than image previews.

**Tech Stack:** FastAPI/Pydantic, Python filesystem storage and persistence layer, Next.js/React, TypeScript, Node test runner, pytest.

## Global Constraints

- Accept UTF-8 `.txt` and `.md` files only; `.docx`, `.pdf`, `.rtf`, and other document formats remain unsupported.
- Preserve existing image formats and image enrichment behavior.
- Keep platform-admin authorization on Reference Pack endpoints.
- Text references do not consume fixed image quota and do not enter the image enrichment worker.
- API responses and audit metadata must not expose private storage paths, raw bytes, or base64 data.
- Use the existing Reference Pack title and pack metadata fields; do not create a second text-only Reference Pack API.

---

### Task 1: Add backend text-upload handling

**Files:**
- Modify: `services/campaign_service/app/main.py:6776-6837` — branch Reference Pack uploads by supported image/text type and persist text metadata.
- Modify: `services/campaign_service/app/main.py` near upload validation helpers — add a small extension/MIME classifier and UTF-8 text reader if the existing helpers cannot express the new contract.
- Modify: `services/campaign_service/app/persistence.py` only if the existing knowledge-item persistence cannot store the text item using the current `metadata`, `content_url`, `file_size`, and `reference_pack_id` fields.
- Test: `services/campaign_service/test_reference_packs.py` and/or a focused `services/campaign_service/test_reference_pack_text.py`.

**Interfaces:**
- Consumes: existing `upload_reference_pack_item(req, pack_id, title, file)` and `_require_platform_admin` authorization.
- Produces: the existing `ReferencePackItemRecord` response with `file_type` `text/plain` or `text/markdown`, `analysis=None` for text, and a sanitized `content_url`.

- [ ] **Step 1: Write failing backend tests for `.txt` and `.md`.**

Add tests that call the existing route with platform-admin authorization and multipart files named `brand-guidelines.txt` and `campaign-notes.md`. Assert status `200`, correct filename/type/size, `analysis is None`, `stored_path` is absent from the JSON response, and the persisted knowledge item has `reference_pack_id` and the expected text file metadata.

```python
def test_reference_pack_text_upload_persists_without_image_analysis(configured, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())
    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Brand guidelines"},
        files={"file": ("brand-guidelines.txt", "Use the approved brand tone.".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "text/plain"
    assert body["analysis"] is None
    assert "stored_path" not in body
```

Add equivalent `.md` coverage and assert the image-enrichment enqueue hook is not called for either text upload.

- [ ] **Step 2: Run the focused tests and confirm they fail for the current image-only implementation.**

Run: `python -m pytest -q services/campaign_service/test_reference_packs.py -k "text_upload"`

Expected: FAIL because the current endpoint returns `400 UNSUPPORTED_FILE_TYPE` for text extensions.

- [ ] **Step 3: Implement the minimal classifier and text persistence branch.**

Use the filename extension plus normalized MIME type. Accept `.txt` with `text/plain` and `.md` with `text/markdown`, while accepting browser-compatible `application/octet-stream` only when the extension is `.txt` or `.md`. Read the upload stream with the existing size and timeout limits, decode as UTF-8 strictly, and delete the partial file on validation failure. Store text using the same knowledge-item persistence path and metadata shape as images, but do not call `_create_pending_analysis` or `_enqueue_best_effort` for text. Keep the current image branch unchanged.

- [ ] **Step 4: Add rejection, encoding, permission, and regression tests.**

Cover `.docx`, `.pdf`, and `.exe` rejection; mismatched image/text MIME and extension rejection; invalid UTF-8 rejection; non-platform-admin `403`; sanitized response fields; and existing image upload enqueue behavior.

- [ ] **Step 5: Run the backend focused suite.**

Run: `python -m pytest -q services/campaign_service/test_reference_packs.py services/campaign_service/test_image_enrichment_routes.py`

Expected: all tests pass.

- [ ] **Step 6: Commit the backend change.**

```bash
git add services/campaign_service/app/main.py services/campaign_service/app/persistence.py services/campaign_service/test_reference_packs.py services/campaign_service/test_image_enrichment_routes.py services/campaign_service/test_reference_pack_text.py
git commit -m "feat: support platform text reference uploads"
```

### Task 2: Preserve text references in RAG context without image quota usage

**Files:**
- Modify: `services/campaign_service/app/context_assembler.py` at platform knowledge/reference selection and serialization helpers.
- Modify: `services/campaign_service/app/main.py` at platform knowledge context assembly only if the existing text-reference path needs a source label or content extraction adjustment.
- Test: `services/campaign_service/test_context_assembler.py` and the relevant campaign-service context/prompt test module.

**Interfaces:**
- Consumes: persisted platform knowledge items with `reference_pack_id`, `file_type` `text/plain` or `text/markdown`, and private backend storage.
- Produces: textual context/provenance for RAG while excluding text items from visual anchor lists, fixed image quotas, and multimodal image payloads.

- [ ] **Step 1: Write failing context tests.**

Create a platform item with a temporary UTF-8 text file and image items in the same Reference Pack. Assert the text is included in the textual reference context/provenance, the image selection counts remain unchanged, and the text item is absent from `image_assets`, `visual_anchors`, and image audit counts.

- [ ] **Step 2: Run the focused context tests and confirm the current behavior fails or omits the text item.**

Run: `python -m pytest -q services/campaign_service/test_context_assembler.py -k "text_reference or reference_pack"`

- [ ] **Step 3: Implement the smallest context change.**

Classify `text/plain` and `text/markdown` as textual knowledge references. Read their stored UTF-8 content only inside backend context assembly, apply the existing prompt/audit sanitization rules, and leave visual selection predicates image-only. Keep private storage paths out of serialized context/audit responses.

- [ ] **Step 4: Run context and image contract tests.**

Run: `python -m pytest -q services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py`

Expected: all tests pass.

- [ ] **Step 5: Commit the context change.**

```bash
git add services/campaign_service/app/context_assembler.py services/campaign_service/app/main.py services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py
git commit -m "feat: include platform text references in RAG context"
```

### Task 3: Update Content Studio upload UI for text files

**Files:**
- Modify: `app/content-studio/page.tsx:623` and the related upload state/rendering code around `uploadFiles` — accept `.txt`/`.md`, classify text files, and render their file state without image-only wording.
- Modify: `lib/api/campaigns.ts:1331-1347` only if the existing multipart client needs a type-safe title or metadata adjustment; keep the endpoint unchanged.
- Modify: `lib/i18n/translations.ts` in English, Traditional Chinese, and Japanese Reference Pack strings — supported format, selected-file, upload, and text-item labels.
- Test: `scripts/check-reference-pack-form-contract.mjs` or the existing frontend test file that covers Content Studio contracts.

**Interfaces:**
- Consumes: existing `uploadReferencePackItems`, `BatchUploadFileState<File>`, and Reference Pack item response.
- Produces: a file picker accepting `image/png,image/jpeg,image/webp,image/gif,text/plain,text/markdown,.txt,.md`, visible format guidance, and text item rows with file metadata.

- [ ] **Step 1: Add a failing frontend contract test.**

Extend the Reference Pack form contract check to assert that the file input accepts `.txt` and `.md`, the UI copy mentions text formats, and the existing image formats remain present.

```js
assert.match(content, /image\/png/);
assert.match(content, /text\/plain/);
assert.match(content, /\.txt/);
assert.match(content, /\.md/);
```

- [ ] **Step 2: Run the contract test and confirm it fails against the current image-only accept list.**

Run: `node scripts/check-reference-pack-form-contract.mjs`

- [ ] **Step 3: Implement the UI changes.**

Replace image-only validation with an extension/MIME classifier matching the backend contract. Keep the existing upload concurrency and retry state. Use a text/file icon or neutral placeholder for text items and do not attempt image preview or image-only analysis status rendering. Update translated labels without changing unrelated campaign copy.

- [ ] **Step 4: Run the contract test and frontend build.**

Run: `node scripts/check-reference-pack-form-contract.mjs` and `npm run build` from the repository frontend package directory used by the deployment image.

Expected: contract check passes and the Next.js build exits `0`.

- [ ] **Step 5: Commit the UI change.**

```bash
git add app/content-studio/page.tsx lib/api/campaigns.ts lib/i18n/translations.ts scripts/check-reference-pack-form-contract.mjs
git commit -m "feat: allow text files in reference pack UI"
```

### Task 4: Run complete verification and deploy

**Files:**
- Verify: `services/campaign_service`, `app/content-studio`, and deployment compose configuration; no additional source changes unless a verification failure identifies a scoped defect.

- [ ] **Step 1: Run the complete campaign-service suite.**

Run from repository root with the project on `PYTHONPATH`: `python -m pytest -q services/campaign_service`

Expected: no failures; existing skips/warnings may remain.

- [ ] **Step 2: Run frontend tests and build.**

Run the repository’s existing frontend test command, `node scripts/check-reference-pack-form-contract.mjs`, and the same production build command used by `deploy/Dockerfile.frontend`.

- [ ] **Step 3: Run diff and status checks.**

Run: `git diff --check` and `git status --short`. Do not stage generated `tsconfig.tsbuildinfo`, `next-env.d.ts`, artifact screenshots, or unrelated existing plan files.

- [ ] **Step 4: Build and restart the affected GCP services.**

Fetch the feature branch on the VM, build `campaign-service`, `worker-image`, `frontend`, and `context-viewer` with the existing deployment compose file, then recreate the affected services.

- [ ] **Step 5: Execute production smoke checks.**

Verify `/content-studio` returns `200`, unauthenticated Reference Pack API access is rejected, authenticated platform-admin upload of a temporary `.txt` and `.md` succeeds, the response contains no private path or binary payload, and the temporary item/pack is deleted afterward. Verify an image upload still returns the existing image analysis behavior.

- [ ] **Step 6: Record the deployed commit and test evidence.**

Report the commit, build result, focused/complete test counts, API statuses, and any known limitations without recording credentials or tokens.
