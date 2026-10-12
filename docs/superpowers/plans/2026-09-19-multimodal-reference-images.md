# Multimodal Reference Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send a deterministic set of actual Reference images to the image worker/provider and block generation when selected images cannot be attached.

**Architecture:** Campaign-service owns Reference selection, file validation, resizing/encoding, and audit metadata. The image worker receives a typed `reference_images` list and builds Gemini multimodal parts; existing prompt-only behavior remains valid only when no references were selected. Copywriting and other workers remain unchanged.

**Tech Stack:** FastAPI/Pydantic, Python `httpx`, Pillow if already available or standard image validation, Gemini image provider, pytest, Docker Compose GCP.

## Global Constraints

- Select at most 6 images: up to 4 campaign/manual references and up to 2 matching-folder references.
- Use deterministic selection; do not call another LLM or embedding model.
- Manual campaign references have priority over industry-matched folder references.
- If a selected Reference cannot be read, validated, or attached, block image generation.
- Do not log image bytes, credentials, signed URLs, or secrets.
- Copywriting and other task types remain unchanged.

---

### Task 1: Add deterministic Reference selection and encoding tests

**Files:**
- Modify: `services/campaign_service/test_context_assembler.py`
- Modify: `services/campaign_service/test_task6_routes.py`
- Test: `services/campaign_service/test_context_assembler.py`

**Interfaces:**
- Produces: a tested image-reference selection/encoding helper used by image worker payload construction.

- [ ] **Step 1: Add failing tests for priority, cap, and missing-file failure**

Cover these cases:

```python
def test_image_reference_selection_prefers_campaign_references_and_caps_at_six():
    # 5 campaign references + 4 industry references -> 4 campaign + 2 industry
    # assert stable ordering and source types

def test_image_reference_selection_rejects_missing_selected_file():
    # selected image with a missing stored_path -> explicit attachment error
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_task6_routes.py -q
```

Expected: FAIL because image reference selection/encoding is not implemented.

- [ ] **Step 3: Implement the minimal campaign-service helper**

Add a helper that filters `image/*` MIME types, verifies `stored_path`, applies a byte/dimension limit, computes a SHA-256 hash, and returns at most four `campaign_reference` items followed by at most two `industry_matched` items. Return structured failures instead of silently dropping selected files.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same pytest command and expect all focused tests to pass.

### Task 2: Add multimodal image worker contract

**Files:**
- Modify: `services/worker_image/app/schemas.py`
- Modify: `services/worker_image/app/main.py`
- Modify: `services/worker_image/test_provider_contract.py`
- Create or modify: `services/worker_image/test_reference_images.py`

**Interfaces:**
- Consumes: `ImageRunRequest.reference_images: list[ReferenceImage]`.
- Produces: provider-ready Gemini image parts and an error response when a required attachment fails.

- [ ] **Step 1: Add failing worker tests**

Test that:

```python
def test_image_worker_passes_reference_images_to_gemini_request():
    # request contains one image part and text prompt
    # assert provider body contains inline image data and MIME type

def test_image_worker_rejects_reference_attachment_failure():
    # a selected reference with attachment_error raises a terminal HTTP error
```

- [ ] **Step 2: Run worker tests and verify RED**

Run:

```powershell
python -m pytest services/worker_image/test_provider_contract.py services/worker_image/test_reference_images.py -q
```

Expected: FAIL because the request schema and provider call currently accept only text prompts.

- [ ] **Step 3: Extend the schema and Gemini request builder**

Add a typed ReferenceImage model containing `reference_id`, `file_name`, `mime_type`, `data`, `folder`, and optional `sha256`. Build Gemini content parts with the text prompt followed by each image’s inline data. Keep prompt-only behavior only when `reference_images` is empty.

- [ ] **Step 4: Make attachment failures terminal**

Reject payloads with selected references that contain failed attachment metadata; return a clear 4xx/5xx detail that includes counts and reference IDs but not file bytes or secrets.

- [ ] **Step 5: Run worker tests and verify GREEN**

Run the focused worker pytest command again and expect all tests to pass.

### Task 3: Connect campaign-service payloads and audit data

**Files:**
- Modify: `services/campaign_service/app/main.py`
- Modify: `services/campaign_service/app/context_assembler.py`
- Modify: `services/campaign_service/test_context_assembler.py`
- Modify: `services/campaign_service/test_worker_result_state.py`

**Interfaces:**
- Consumes: the deterministic image-reference helper from Task 1 and `GenerationContextSnapshot` items.
- Produces: image worker payloads with `reference_images`, selected/attached counts, hashes, and failure metadata.

- [ ] **Step 1: Add a failing payload contract test**

Assert that `build_worker_payload_for_task(..., task_type="image_generation", snapshot=...)` includes actual encoded image data, MIME types, selected IDs, and audit counts, while a missing selected file raises before dispatch.

- [ ] **Step 2: Run the payload test and verify RED**

Run:

```powershell
python -m pytest services/campaign_service/test_context_assembler.py services/campaign_service/test_worker_result_state.py -q
```

- [ ] **Step 3: Implement image-only payload enrichment**

When `task_type` is `image_generation`, resolve and encode the selected image files, attach `reference_images`, and include an audit object such as `reference_audit` with selected IDs, attached count, failed IDs/categories, and multimodal status. Do not add image bytes to prompts or to log output.

- [ ] **Step 4: Persist terminal attachment failure state**

Ensure the worker dispatch path records attachment failures as failed image tasks and never persists a normal generated asset for a failed attachment request.

- [ ] **Step 5: Run campaign-service focused tests and verify GREEN**

Run the focused command again and expect all tests to pass.

### Task 4: Full verification and GCP deployment

**Files:**
- Deploy: `services/campaign_service/app/context_assembler.py`
- Deploy: `services/campaign_service/app/main.py`
- Deploy: `services/worker_image/app/schemas.py`
- Deploy: `services/worker_image/app/main.py`

- [ ] **Step 1: Run service regression suites**

Run:

```powershell
python -m pytest services/campaign_service -q
python -m pytest services/worker_image -q
```

- [ ] **Step 2: Build the changed service images**

Build `campaign-service` and `worker-image` with the existing GCP Compose file and confirm both images compile.

- [ ] **Step 3: Deploy only the changed services**

Restart only `campaign-service` and `worker-image`; do not restart the database or unrelated workers.

- [ ] **Step 4: Verify service health and audit behavior**

Confirm containers are running, `/campaigns` remains HTTP `200`, and a controlled image-generation smoke request reports the selected/attached Reference counts without exposing image bytes or credentials.
