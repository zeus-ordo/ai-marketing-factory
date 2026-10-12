# System Reference Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let platform administrators manage categorized system Reference Packs and automatically select a bounded set of platform images for campaign generation.

**Architecture:** Add a platform-scoped `reference_packs` table and link existing stored Knowledge items to Packs. Expose protected Pack CRUD/upload endpoints and a platform-admin section in Content Studio. Extend generation-context assembly to merge mandatory platform Packs, applicable optional Packs, campaign References, and existing company matches under a hard six-image limit, with sanitized audit metadata.

**Tech Stack:** FastAPI, PostgreSQL, existing file storage/Knowledge persistence, Next.js/React, TypeScript, pytest, Node test runner.

## Global Constraints

- Only platform administrators may create, update, delete, or upload into platform Packs.
- Roles: `brand_identity`, `product`, `style`, `composition`, `campaign_examples`.
- Selection modes: `mandatory` and `optional`.
- Hard total: 6 image References per generation.
- Mandatory `brand_identity`: up to 2; mandatory `product`: up to 2.
- Image bytes remain transient and are never persisted in context metadata or exposed by Context Viewer.
- Optional missing files are skipped and audited; mandatory missing files fail generation with structured 422.
- First version uses deterministic Pack metadata and rotation, not a vector database.

---

### Task 1: Persist and manage Reference Packs

**Files:**
- Modify: `services/campaign_service/app/persistence.py`
- Modify: `services/campaign_service/app/main.py`
- Test: `services/campaign_service/test_persistence_migrations.py`
- Create: `services/campaign_service/test_reference_packs.py`

**Interfaces:**
- Consumes existing `PostgresPersistence`, `is_platform_admin_request`, and Knowledge upload/storage functions.
- Produces `ReferencePackRecord`, Pack CRUD methods, and protected Pack upload/list routes.

- [ ] **Step 1: Write failing tests**

Test the `reference_packs` schema, platform-admin creation/listing, non-admin 403, invalid role/limit 400, and Pack-linked image upload metadata.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest -q services/campaign_service/test_reference_packs.py services/campaign_service/test_persistence_migrations.py
```

Expected: FAIL because the table, schemas, and routes do not exist.

- [ ] **Step 3: Add migration and persistence methods**

Add `reference_packs` with `pack_id`, `name`, `role`, `scope`, `industry`, `selection_mode`, `max_images`, `priority`, `is_active`, `created_at`, and `updated_at`. Link uploaded Knowledge items with `reference_pack_id` and Pack metadata while keeping stored paths private.

- [ ] **Step 4: Add protected routes**

Implement:

```text
GET    /api/v1/reference-packs
POST   /api/v1/reference-packs
PATCH  /api/v1/reference-packs/{pack_id}
DELETE /api/v1/reference-packs/{pack_id}
GET    /api/v1/reference-packs/{pack_id}/items
POST   /api/v1/reference-packs/{pack_id}/items/upload
DELETE /api/v1/reference-packs/{pack_id}/items/{item_id}
```

Every route calls `is_platform_admin_request`; upload reuses image MIME/size validation and existing file storage.

- [ ] **Step 5: Verify GREEN and commit**

Run the focused tests, then commit:

```powershell
git add services/campaign_service/app/persistence.py services/campaign_service/app/main.py services/campaign_service/test_persistence_migrations.py services/campaign_service/test_reference_packs.py
git commit -m "Add platform reference pack management"
```

### Task 2: Add the platform-admin Pack management UI

**Files:**
- Modify: `lib/api/campaigns.ts`
- Modify: `app/content-studio/page.tsx`
- Modify: `lib/i18n/translations.ts`
- Test: existing frontend API/batch-upload tests

**Interfaces:**
- Consumes Task 1 Pack endpoints and existing `uploadBatchItems`/`FilePreviewModal` patterns.
- Produces a platform-admin-only System Reference Packs section.

- [ ] **Step 1: Write failing API contract tests**

Assert typed helpers use `/api/v1/reference-packs`, multipart upload, role/industry/selection mode, Pack image listing, and stable per-file upload errors.

- [ ] **Step 2: Verify RED**

Run:

```powershell
node --experimental-strip-types --test context-viewer/test/query.test.ts
```

Expected: the new Pack API contract assertions fail.

- [ ] **Step 3: Add typed API helpers**

Add Pack record/types and list/create/update/delete/list-items/upload/delete-item functions. Never return stored filesystem paths.

- [ ] **Step 4: Add the Content Studio section**

Show `System Reference Packs` only to platform administrators. Support Pack creation/editing, role, industry, mandatory/optional mode, max images, priority, multi-file upload, preview, deletion, filters, counts, loading, and errors.

- [ ] **Step 5: Add translations and verify**

Add English, Traditional Chinese, and Japanese labels. Run frontend tests and production build:

```powershell
npm test
npm run build
```

- [ ] **Step 6: Commit**

```powershell
git add lib/api/campaigns.ts app/content-studio/page.tsx lib/i18n/translations.ts
git commit -m "Add system reference pack admin UI"
```

### Task 3: Select Pack images during generation and persist audit

**Files:**
- Modify: `services/campaign_service/app/context_assembler.py`
- Modify: `services/campaign_service/app/main.py`
- Test: `services/campaign_service/test_context_assembler.py`
- Test: `services/campaign_service/test_image_generation_contract.py`

**Interfaces:**
- Consumes active Pack rows and Pack-linked Knowledge metadata.
- Produces `select_reference_pack_items(items, campaign_id, run_id, total_limit=6)` and Pack-aware `reference_audit`.

- [ ] **Step 1: Write failing selection tests**

Cover mandatory brand/product priority, optional Pack filling, deterministic rotation by campaign/run, SHA-256 duplicate removal, six-image cap, optional missing files, and mandatory missing-file 422.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest -q services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py -k "pack or reference"
```

- [ ] **Step 3: Implement deterministic selection**

Load global and matching-industry Packs before company matching. Sort by priority and a stable rotation hash of `campaign_id`, `run_id`, and `pack_id`; deduplicate by SHA-256; enforce six total images; preserve manual campaign Reference priority over optional Pack items.

- [ ] **Step 4: Integrate source and audit metadata**

Use source types `platform_default` and `industry_default`. Record candidate count, selected/attached counts, policy version, Pack ID, role, selection mode, reason, priority, file metadata, SHA-256, and failures. Persist only sanitized metadata, never bytes.

- [ ] **Step 5: Verify and commit**

Run focused tests and the full campaign-service suite:

```powershell
python -m pytest -q services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py
python -m pytest -q services/campaign_service
```

Then commit:

```powershell
git add services/campaign_service/app/context_assembler.py services/campaign_service/app/main.py services/campaign_service/test_context_assembler.py services/campaign_service/test_image_generation_contract.py
git commit -m "Select bounded images from reference packs"
```

### Task 4: Show Pack provenance, deploy, and verify

**Files:**
- Modify: `context-viewer/app/page.tsx`
- Test: `context-viewer/test/query.test.ts`

- [ ] **Step 1: Write failing viewer tests**

Assert that audit renders `platform_default`/`industry_default`, Pack ID/name, role, mandatory/optional mode, selection reason, priority, candidate count, selected count, and no image bytes; preserve legacy activities.

- [ ] **Step 2: Verify RED and implement safe rendering**

Run `npm test` in `context-viewer`, then add normalized Pack provenance rendering while retaining recursive server-side binary sanitization.

- [ ] **Step 3: Verify frontend**

Run from `context-viewer`:

```powershell
npm test
npm run build
```

- [ ] **Step 4: Commit viewer changes**

```powershell
git add context-viewer/app/page.tsx context-viewer/test/query.test.ts
git commit -m "Show reference pack provenance in context viewer"
```

- [ ] **Step 5: Deploy affected services**

Push the branch, reset the GCP checkout to the pushed commit, and run without printing secrets:

```powershell
docker compose -f deploy/docker-compose.gcp.yml up -d --build campaign-service worker-image context-viewer
```

- [ ] **Step 6: Verify production behavior**

Check container status/logs, create one mandatory Brand Identity Pack and one optional Style Pack, create a test campaign, and confirm Context Viewer shows Pack provenance with no more than six attached images.

- [ ] **Step 7: Run final tests and push**

Run all affected service suites, `git diff --check`, then:

```powershell
git push origin feature/complete-campaign-flow
```
