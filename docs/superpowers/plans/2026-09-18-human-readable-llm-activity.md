# Human-Readable LLM Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present Context Viewer activity details as readable “what we sent” and “what the LLM returned” sections while preserving technical details for administrators.

**Architecture:** Keep the existing API and persisted data unchanged. Add small deterministic formatting helpers in the Context Viewer page to project payloads, context items, external sources, and outputs into customer-facing text; keep raw JSON and identifiers inside a collapsed technical section.

**Tech Stack:** Next.js 16, React 19, TypeScript, Node test runner, existing Context Viewer API/database queries.

## Global Constraints

- Use a deterministic presentation layer; do not call another LLM.
- Preserve the original language of prompts, references, and model responses.
- Show complete readable content, not only keywords or generated summaries.
- Keep raw technical fields in a collapsed technical-details section.
- Never infer missing historical prompt content.
- Preserve authentication, filtering, redaction, and existing copy/download actions.

---

### Task 1: Add formatting regression tests

**Files:**
- Modify: `context-viewer/test/query.test.ts`
- Test: `context-viewer/test/query.test.ts`

- [ ] **Step 1: Add assertions for readable sections and historical fallback**

Extend the existing page contract tests to require the customer-facing labels “What we sent to the AI” and “What the AI returned”, a collapsed technical-details element, readable reference fields, and the existing missing-prompt fallback sentence.

- [ ] **Step 2: Run the focused tests before implementation**

Run:

```powershell
node --test context-viewer/test/query.test.ts
```

Expected: FAIL because the current page uses the old labels and exposes the prompt/context panels without the new separation contract.

### Task 2: Implement readable activity presentation

**Files:**
- Modify: `context-viewer/app/page.tsx`
- Modify: `context-viewer/app/globals.css` if existing styles cannot express the two primary sections and technical disclosure.

**Interfaces:**
- Consumes: `Detail.payloads`, `Detail.items`, `Detail.outputs`, `external_source_urls_json`, and persisted status fields.
- Produces: readable input/output sections, readable reference rows, and a collapsed technical-details section without changing API response shapes.

- [ ] **Step 1: Add deterministic display helpers**

Keep prompt text as-is when captured. Normalize context items into filename/label, folder, source type, and readable text/query. Normalize outputs into readable copy, asset names/links, ads strategy metadata, validation status, and failure details. Use the explicit historical fallback when no prompt payload exists.

- [ ] **Step 2: Replace the primary detail layout**

Render two prominent panels:

```tsx
<DetailPanel title="What we sent to the AI" ... />
<DetailPanel title="What the AI returned" ... />
```

The sent panel must show the complete prompt plus supplied Reference names/folders and external search information without database IDs, token counts, task IDs, or JSON wrappers.

- [ ] **Step 3: Add the collapsed technical section**

Use native `<details>`/`<summary>` to hold raw payload JSON, context JSON, generation context ID, run ID, token counts/ratios, provider, model, and task ID. Keep existing raw JSON download available inside this section.

- [ ] **Step 4: Preserve current actions**

Keep copy/download actions for prompt, outputs, and raw JSON. Keep authentication, filtering, redaction, and historical fallback behavior unchanged.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
node --test context-viewer/test/query.test.ts
```

Expected: PASS.

### Task 3: Build and deploy Context Viewer

**Files:**
- Deploy: `context-viewer/app/page.tsx`
- Deploy: `context-viewer/app/globals.css` when modified.

- [ ] **Step 1: Build the viewer locally**

Run the Context Viewer package build command from `context-viewer` and verify TypeScript/build success.

- [ ] **Step 2: Copy changed viewer files to the GCP VM**

Copy only the changed viewer source files to `/opt/ai-marketing-factory/context-viewer/` without printing viewer credentials or database URLs.

- [ ] **Step 3: Rebuild and restart only Context Viewer**

Run on the VM:

```bash
cd /opt/ai-marketing-factory
docker compose -f deploy/docker-compose.gcp.yml build context-viewer
docker compose -f deploy/docker-compose.gcp.yml up -d context-viewer
```

- [ ] **Step 4: Verify public viewer availability**

Run:

```powershell
curl.exe -sS -o NUL -w "viewer HTTP:%{http_code}\n" http://35.221.249.149:3010/
```

Expected: HTTP `200` or the configured login redirect response.
