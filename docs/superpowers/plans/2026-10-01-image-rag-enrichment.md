# Image RAG Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze only newly uploaded images asynchronously into structured RAG attributes and embeddings, then use attributes plus at most three visual anchors during generation.

**Architecture:** Persist an analysis record keyed by `knowledge_items.item_id`; uploads enqueue an idempotent Redis enrichment job and return `pending`. A dedicated enrichment worker reads the private image path, calls isolated multimodal-analysis and embedding provider interfaces, and persists `ready` or retryable `failed` state. Context assembly retrieves only ready enriched items, emits attributes for text tasks, and attaches at most three anchors for image tasks while preserving existing mandatory Pack limits.

**Tech Stack:** FastAPI, Pydantic, psycopg/PostgreSQL, Redis Streams, Python provider adapters, Next.js/TypeScript, pytest, Vitest/contract scripts.

## Global Constraints

- Existing Knowledge items are not backfilled and remain on the current legacy path.
- Upload success is independent of analysis success.
- Pending/failed new items are excluded from the new RAG retrieval path.
- Image tasks receive at most three enriched visual anchors plus mandatory Reference Pack images, and the existing six-image hard cap remains authoritative.
- Persisted metadata, API responses, audit records, and Context Viewer output must never include image bytes, base64 data, or private storage paths.
- Analysis jobs are idempotent by Knowledge item ID and analysis version.
- If vector search is unavailable, deterministic metadata matching among ready items remains available and uploads are not blocked.

---

### Task 1: Add analysis schema and persistence boundary

**Files:**
- Modify: `services/campaign_service/app/persistence.py:303-375, 2950-3067`
- Modify: `services/campaign_service/app/schemas.py` (Knowledge item and response models)
- Create: `services/campaign_service/app/image_enrichment.py`
- Test: `services/campaign_service/test_image_enrichment_persistence.py`
- Test: `services/campaign_service/test_persistence_migrations.py`

**Interfaces:**
- Produce `ImageAnalysisRecord` with `item_id`, `analysis_status`, `analysis_version`, `attributes`, `embedding_status`, `embedding_model`, `embedding_dimension`, `error_code`, `error_detail`, `attempt_count`, `analyzed_at`, and `updated_at`.
- Produce `Persistence.create_image_analysis(item_id: str, analysis_version: str) -> dict[str, Any]`.
- Produce `Persistence.claim_image_analysis(item_id: str, analysis_version: str) -> bool` using a conditional `pending`/retryable update.
- Produce `Persistence.complete_image_analysis(item_id: str, analysis_version: str, attributes: dict[str, Any], embedding: list[float] | None, embedding_model: str | None) -> dict[str, Any]`.
- Produce `Persistence.fail_image_analysis(item_id: str, analysis_version: str, error_code: str, error_detail: str) -> dict[str, Any]`.
- Produce `Persistence.get_image_analysis(item_id: str) -> dict[str, Any] | None` and `list_ready_image_analysis(company_id: str, industry: str | None, limit: int) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write failing persistence and schema tests**

```python
def test_new_analysis_starts_pending(persistence):
    row = persistence.create_image_analysis("kh_new", "image-rag-v1")
    assert row["analysis_status"] == "pending"
    assert row["analysis_version"] == "image-rag-v1"

def test_ready_listing_excludes_pending_and_failed(persistence):
    persistence.create_image_analysis("kh_pending", "image-rag-v1")
    persistence.create_image_analysis("kh_failed", "image-rag-v1")
    persistence.fail_image_analysis("kh_failed", "image-rag-v1", "PROVIDER_ERROR", "retry")
    assert persistence.list_ready_image_analysis("company-1", "food", 20) == []
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py -q`

Expected: FAIL because the analysis table, model, and persistence methods do not exist.

- [ ] **Step 3: Add the migration and persistence methods**

Create `knowledge_item_image_analysis` with a unique `(item_id, analysis_version)`, JSONB attributes, optional vector column behind a safe migration, status checks, retry fields, and indexes for `(company_id, analysis_status, industry)`. Ensure `list_ready_image_analysis` joins `knowledge_items`, filters `deleted_at IS NULL`, scope, industry, and `analysis_status='ready'`.

- [ ] **Step 4: Add safe public schema fields**

Expose only status, version, attribute summary, retry availability, and analyzed timestamp through `KnowledgeItemRecord`; keep stored paths and vectors internal.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `pytest services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/campaign_service/app/persistence.py services/campaign_service/app/schemas.py services/campaign_service/app/image_enrichment.py services/campaign_service/test_image_enrichment_persistence.py services/campaign_service/test_persistence_migrations.py
git commit -m "feat: persist image enrichment state"
```

### Task 2: Implement provider adapters and enrichment worker

**Files:**
- Create: `services/worker_enrichment/app/main.py`
- Create: `services/worker_enrichment/app/providers.py`
- Create: `services/worker_enrichment/requirements.txt`
- Create: `services/worker_enrichment/Dockerfile`
- Modify: `services/campaign_service/app/image_enrichment.py`
- Test: `services/worker_enrichment/test_provider_contract.py`
- Test: `services/worker_enrichment/test_enrichment_job.py`

**Interfaces:**
- `ImageAnalysisProvider.analyze(image_path: str, mime_type: str, title: str, description: str) -> dict[str, Any]` returns schema-validated attributes only.
- `EmbeddingProvider.embed(text: str) -> list[float]` returns a finite vector or raises a classified provider error.
- `process_image_enrichment_job(payload: dict[str, Any]) -> dict[str, Any]` claims the record, reads the private path transiently, persists attributes/embedding, and returns status.
- `POST /internal/v1/image-enrichment` accepts `{item_id, analysis_version}` and returns `{item_id, status}` without returning image data or paths.

- [ ] **Step 1: Write failing provider and job tests**

```python
def test_job_transitions_pending_to_ready(monkeypatch, analysis_store, tmp_path):
    image = tmp_path / "new.png"
    image.write_bytes(b"png")
    analysis_store.add_item("kh_new", str(image), "image/png")
    monkeypatch.setattr("app.providers.analysis_provider", FakeAnalysisProvider())
    monkeypatch.setattr("app.providers.embedding_provider", FakeEmbeddingProvider())
    result = process_image_enrichment_job({"item_id": "kh_new", "analysis_version": "image-rag-v1"})
    assert result["status"] == "ready"

def test_provider_failure_is_retryable(monkeypatch, analysis_store):
    monkeypatch.setattr("app.providers.analysis_provider", FailingProvider())
    result = process_image_enrichment_job({"item_id": "kh_fail", "analysis_version": "image-rag-v1"})
    assert result["status"] == "failed"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest services/worker_enrichment/test_provider_contract.py services/worker_enrichment/test_enrichment_job.py -q`

Expected: FAIL because the worker package and provider interfaces do not exist.

- [ ] **Step 3: Implement strict provider adapters**

Validate returned attributes against a Pydantic model with bounded strings/lists and no binary fields. Build embedding input from the canonical JSON attributes, not raw image bytes. Keep provider/model names configurable through environment variables.

- [ ] **Step 4: Implement idempotent job handling**

Claim before provider calls; return `already_complete` for a ready record, delete no files on provider failure, redact exception details before persistence, and always remove transient bytes from memory references after processing.

- [ ] **Step 5: Add the internal worker endpoint and container**

Use the same health/auth conventions as `services/worker_copy` and `services/worker_image`. The endpoint must reject missing item IDs, never echo `stored_path`, and classify provider, timeout, and invalid-schema failures.

- [ ] **Step 6: Run focused tests and commit**

Run: `pytest services/worker_enrichment/test_provider_contract.py services/worker_enrichment/test_enrichment_job.py -q`

Expected: PASS.

```bash
git add services/worker_enrichment services/campaign_service/app/image_enrichment.py
git commit -m "feat: add asynchronous image enrichment worker"
```

### Task 3: Enqueue uploads and expose retry/status APIs

**Files:**
- Modify: `services/campaign_service/app/main.py:6431-6491, 6375-6395, 6522-6557`
- Modify: `services/campaign_service/app/persistence.py`
- Modify: `services/campaign_service/app/schemas.py`
- Modify: `services/orchestrator/app/main.py` (Redis stream dispatch and worker URL map)
- Create: `services/campaign_service/test_image_enrichment_routes.py`
- Modify: `services/orchestrator/test_task_failure_isolation.py`

**Interfaces:**
- `enqueue_image_enrichment(item_id: str, analysis_version: str) -> None` publishes to the existing Redis stream/queue with a deduplication key.
- `POST /api/v1/knowledge-items/{item_id}/analysis/retry` resets a failed analysis and enqueues one job.
- `GET /api/v1/knowledge-items/{item_id}/analysis` returns safe analysis status and summary.

- [ ] **Step 1: Write failing route tests**

```python
def test_upload_returns_pending_and_enqueues(monkeypatch, client):
    published = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda item_id, version: published.append((item_id, version)))
    response = client.post("/api/v1/knowledge-items/upload", files={"file": ("new.png", b"png", "image/png")}, data={"title": "New"})
    assert response.status_code == 200
    assert response.json()["analysis"]["analysis_status"] == "pending"
    assert len(published) == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest services/campaign_service/test_image_enrichment_routes.py -q`

Expected: FAIL because upload does not create analysis state or publish a job.

- [ ] **Step 3: Add durable Redis stream dispatch**

Publish `{item_id, analysis_version}` to the existing Redis task stream as `task.image_enrichment`; add the stream to the orchestrator consumer map and dispatch it to `WORKER_ENRICHMENT_URL/internal/v1/image-enrichment`. Reuse the existing claim, retry, acknowledgement, and failure classification behavior rather than starting an in-process FastAPI task.

- [ ] **Step 4: Enqueue after durable persistence**

For `/knowledge-items/upload` and `/reference-packs/{pack_id}/items/upload`, persist the file and Knowledge row, create the pending analysis record, then publish the job. If publishing fails, keep the upload successful and mark the analysis as pending for a later retry/reclaimer.

- [ ] **Step 5: Add status and retry routes**

Apply the same company/platform authorization as the Knowledge item route. Retry only failed records, increment attempt state through the persistence method, and never return private path or vector data.

- [ ] **Step 6: Run tests and commit**

Run: `pytest services/campaign_service/test_image_enrichment_routes.py services/campaign_service/test_batch_upload.py services/orchestrator/test_task_failure_isolation.py -q`

Expected: PASS.

```bash
git add services/campaign_service/app/main.py services/campaign_service/app/persistence.py services/campaign_service/app/schemas.py services/orchestrator/app/main.py services/campaign_service/test_image_enrichment_routes.py services/orchestrator/test_task_failure_isolation.py
git commit -m "feat: enqueue image analysis after upload"
```

### Task 4: Integrate attributes and vector/fallback retrieval

**Files:**
- Modify: `services/campaign_service/app/main.py:2408-2517, 2535-2588`
- Modify: `services/campaign_service/app/context_assembler.py:23-237`
- Create: `services/campaign_service/test_image_rag_retrieval.py`

**Interfaces:**
- `list_enriched_knowledge_context(campaign: CampaignRecord, limit: int = 8) -> list[dict[str, Any]]` returns ready attributes with safe provenance and transient path only in memory.
- `select_visual_anchor_items(items: list[ContextSourceItem], limit: int = 3) -> tuple[ContextSourceItem, ...]` chooses deterministic enriched anchors.
- `build_structured_attribute_text(attributes: dict[str, Any]) -> str` emits bounded, stable prompt text.

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_retrieval_excludes_pending_and_failed(monkeypatch, campaign):
    monkeypatch.setattr(main.persistence, "list_ready_image_analysis", lambda *args: [{"item_id": "ready", "attributes": {"style": ["warm"]}}])
    rows = main.list_enriched_knowledge_context(campaign)
    assert [row["item_id"] for row in rows] == ["ready"]

def test_anchor_selection_is_bounded_and_deterministic():
    selected = select_visual_anchor_items(make_enriched_items(8), limit=3)
    assert len(selected) == 3
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest services/campaign_service/test_image_rag_retrieval.py -q`

Expected: FAIL because enriched retrieval and anchor selection do not exist.

- [ ] **Step 3: Implement ready-only retrieval**

Use metadata scope/industry filters first. Use pgvector similarity when the vector column and query embedding are available; catch vector errors and fall back to deterministic `match_industry_items` ordering among ready items. Include `analysis_version`, role, score, and selection reason in transient metadata.

- [ ] **Step 4: Convert attributes to prompt-safe structured text**

Use labeled JSON or stable `key: values` sections, cap each field and total length, and include source item IDs. Never include `stored_path`, raw OCR beyond its limit, or binary values.

- [ ] **Step 5: Add enriched rows to generation context**

Keep the legacy industry rows for legacy items. Add ready enriched rows as a separate source type so audit can distinguish `industry_attribute_rag` from `industry_matched`. Do not let pending or failed items enter the snapshot.

- [ ] **Step 6: Run tests and commit**

Run: `pytest services/campaign_service/test_image_rag_retrieval.py services/campaign_service/test_context_assembler.py -q`

Expected: PASS.

```bash
git add services/campaign_service/app/main.py services/campaign_service/app/context_assembler.py services/campaign_service/test_image_rag_retrieval.py
git commit -m "feat: retrieve ready image attributes"
```

### Task 5: Split text attributes from visual anchor payloads and audit

**Files:**
- Modify: `services/campaign_service/app/context_assembler.py`
- Modify: `services/campaign_service/app/main.py:2840-2925, 2675-2695`
- Modify: `services/worker_image/app/main.py` and prompt/provider helpers
- Test: `services/campaign_service/test_image_generation_contract.py`
- Test: `services/campaign_service/test_llm_context_capture.py`
- Test: `services/worker_image/test_reference_images.py`

**Interfaces:**
- `build_generation_reference_payload(snapshot: GenerationContextSnapshot, task_type: str) -> dict[str, Any]` returns `{attributes, visual_anchors, legacy_references}` with no stored paths in serialized output.
- `select_image_reference_items` remains compatible for legacy/Pack behavior; enriched anchors are capped at 3 before applying the global six-image cap.

- [ ] **Step 1: Write failing payload tests**

```python
def test_copy_payload_has_attributes_without_image_parts(snapshot):
    payload = build_generation_reference_payload(snapshot, "copywriting")
    assert payload["attributes"]
    assert payload["visual_anchors"] == []

def test_image_payload_has_at_most_three_enriched_anchors(snapshot):
    payload = build_generation_reference_payload(snapshot, "image_generation")
    assert len(payload["visual_anchors"]) <= 3
    assert all("stored_path" not in item for item in payload["visual_anchors"])
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_llm_context_capture.py services/worker_image/test_reference_images.py -q`

Expected: FAIL because generation still treats all selected references uniformly.

- [ ] **Step 3: Implement task-aware payload construction**

For text tasks, serialize only bounded structured attributes and provenance. For image tasks, serialize attributes plus transient image parts from ready anchors and mandatory Pack selections. Preserve manual campaign references and the existing total six-image limit.

- [ ] **Step 4: Update image worker prompt/provider contract**

Accept attributes as textual context and images as separate parts. Keep the existing provider contract for legacy references, but assert that the worker receives no more than six image parts and no private path fields.

- [ ] **Step 5: Extend audit and Context Viewer-safe diagnostics**

Record candidate/selected/attached counts, attribute source IDs, analysis versions, similarity/selection reasons, and anchor hashes. Sanitize recursively before persistence/display.

- [ ] **Step 6: Run tests and commit**

Run: `pytest services/campaign_service/test_image_generation_contract.py services/campaign_service/test_llm_context_capture.py services/worker_image/test_reference_images.py services/worker_image/test_prompt.py -q`

Expected: PASS.

```bash
git add services/campaign_service/app/context_assembler.py services/campaign_service/app/main.py services/worker_image services/campaign_service/test_image_generation_contract.py services/campaign_service/test_llm_context_capture.py
git commit -m "feat: send attributes and bounded visual anchors"
```

### Task 6: Add Content Studio status and retry UI

**Files:**
- Modify: `lib/api/campaigns.ts:1252-1410`
- Modify: `app/content-studio/page.tsx:140-440`
- Modify: `lib/i18n/translations.ts`
- Create: `scripts/test-image-rag-upload-contract.mjs`

**Interfaces:**
- `KnowledgeItemRecord.analysis` contains safe status fields.
- `retryKnowledgeItemAnalysis(itemId: string): Promise<KnowledgeAnalysis>` calls the retry endpoint.
- `getKnowledgeItemAnalysis(itemId: string): Promise<KnowledgeAnalysis>` calls the status endpoint.

- [ ] **Step 1: Write the frontend contract test**

```javascript
assert.match(source, /analysis_status|analysis\.analysis_status/);
assert.match(source, /retryKnowledgeItemAnalysis/);
assert.match(source, /pending|processing|ready|failed/);
```

- [ ] **Step 2: Run and verify failure**

Run: `node scripts/test-image-rag-upload-contract.mjs`

Expected: FAIL because the API helper, status rendering, and retry action do not exist.

- [ ] **Step 3: Add typed API helpers and translations**

Expose only safe fields and localized labels for pending, processing, ready, failed, retry, and attribute preview.

- [ ] **Step 4: Render status and retry controls**

Show status beside each newly uploaded Knowledge/Pack item, disable RAG eligibility messaging until ready, and refresh the item after retry without exposing file paths.

- [ ] **Step 5: Run frontend checks and commit**

Run: `node scripts/test-image-rag-upload-contract.mjs; npm run build`

Expected: PASS and production build succeeds.

```bash
git add lib/api/campaigns.ts app/content-studio/page.tsx lib/i18n/translations.ts scripts/test-image-rag-upload-contract.mjs
git commit -m "feat: show image analysis status in content studio"
```

### Task 7: Wire deployment, end-to-end tests, and verification

**Files:**
- Modify: `deploy/docker-compose.yml:86-120`
- Modify: `deploy/docker-compose.gcp.yml:80-105`
- Modify: `.env.test.local.example`
- Test: `tests_e2e/test_image_rag_enrichment.py`
- Modify: `services/campaign_service/test_reference_packs.py`

- [ ] **Step 1: Add worker service and environment contract**

Build `services/worker_enrichment`, provide Redis/Postgres/campaign-service dependencies, configure provider/model variables, and mount the same private Knowledge upload volume required for transient reads.

- [ ] **Step 2: Write end-to-end tests**

Cover upload -> pending, worker success -> ready, provider failure -> failed, retry -> ready, ready-only retrieval, copy payload without images, image payload with bounded anchors, Pack hard cap, and company/platform isolation.

- [ ] **Step 3: Run all service tests**

Run: `pytest services/campaign_service services/worker_enrichment services/worker_image tests_e2e -q`

Expected: all relevant tests pass; environment-dependent tests are explicitly skipped only when their required service is unavailable.

- [ ] **Step 4: Build containers and run smoke checks**

Run: `docker compose -f deploy/docker-compose.yml build campaign_service worker_enrichment worker_image frontend` then start the stack and verify upload returns pending, status transitions, retry works, and Context Viewer contains provenance without paths or bytes.

- [ ] **Step 5: Deploy GCP configuration and verify**

Run: `docker compose -f deploy/docker-compose.gcp.yml up -d --build campaign_service orchestrator worker_enrichment worker_image frontend`, then verify container health, frontend HTTP 200, campaign service HTTP 200, worker enrichment health, and one new image upload through the production API.

- [ ] **Step 6: Commit deployment and verification changes**

```bash
git add deploy/docker-compose.yml deploy/docker-compose.gcp.yml .env.test.local.example tests_e2e/test_image_rag_enrichment.py services/campaign_service/test_reference_packs.py
git commit -m "test: verify image RAG enrichment flow"
```

## Plan self-review

- Existing data no-backfill requirement is covered by Tasks 1, 3, and 4.
- Async pending/processing/ready/failed lifecycle and retry are covered by Tasks 1–3.
- Provider isolation, embeddings, and vector fallback are covered by Tasks 2 and 4.
- Text-only attributes and bounded visual anchors are covered by Task 5.
- UI status/retry and safe fields are covered by Task 6.
- Deployment, end-to-end tests, and GCP verification are covered by Task 7.
- No task stores image bytes, base64, or private paths in persisted analysis/audit fields.
