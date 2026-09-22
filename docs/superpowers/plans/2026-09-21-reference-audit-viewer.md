# Reference Audit Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist sanitized image Reference attachment audits and display them in the Context Viewer.

**Architecture:** campaign-service adds the non-secret `reference_audit` to the existing persisted context metadata while continuing to send image bytes only in the transient worker payload. Context Viewer reads that metadata from `llm_generation_payloads.context_json`, normalizes legacy/malformed values, and renders a verification summary and per-reference rows.

**Tech Stack:** Python, FastAPI, PostgreSQL JSONB, Next.js/React, TypeScript, Node test runner.

## Global Constraints

- Never persist or render base64 image data.
- Preserve existing behavior for old activities without audit metadata.
- Display selected count, attached count, multimodal state, per-reference SHA-256, and failures.
- Mark success only when selected and attached counts match and failures are empty.

---

### Task 1: Persist the sanitized audit

**Files:**
- Modify: `services/campaign_service/app/main.py:2664-2677`
- Test: `services/campaign_service/test_context_assembler.py`

**Interfaces:**
- Consumes: existing `build_image_reference_payload(snapshot)` return value.
- Produces: `context_json.reference_audit` in the persisted LLM payload, containing only audit metadata.

- [ ] **Step 1: Write the failing test**

Add a test for `build_worker_payload_for_task` with an image task and a snapshot containing one campaign Reference. Assert that the returned payload has `reference_audit` with `selected_count`, `attached_count`, `multimodal`, and a `references` row containing the reference ID, file name, MIME type, folder, and SHA-256, while the persisted context metadata contains the audit but does not contain a `data` field or base64 content.

- [ ] **Step 2: Run the focused test**

Run from `services/campaign_service`:

```powershell
pytest test_context_assembler.py -k "reference_audit" -v
```

Expected: FAIL because `context_payload` does not yet include the audit.

- [ ] **Step 3: Implement the minimal persistence change**

Update `build_image_reference_payload` so its audit includes the sanitized metadata for every successfully attached item:

```python
audit_references = [
    {key: reference[key] for key in ("reference_id", "file_name", "mime_type", "folder", "sha256")}
    for reference in references
]
return references, {
    "selected_count": len(selected),
    "attached_count": len(references),
    "failures": failures,
    "multimodal": bool(references),
    "references": audit_references,
}
```

After `reference_images, reference_audit = ...`, add the audit to `context_payload` only for image-generation tasks:

```python
if task_type == "image_generation":
    context_payload["reference_audit"] = reference_audit
```

Keep `reference_images` as a top-level transient worker field. Do not add `reference_images` or its `data` values to `context_payload`.

- [ ] **Step 4: Run the focused test**

Run:

```powershell
pytest test_context_assembler.py -k "reference_audit" -v
```

Expected: PASS.

- [ ] **Step 5: Run the campaign-service suite**

Run:

```powershell
pytest -q
```

Expected: existing suite passes with the new audit assertion.

- [ ] **Step 6: Commit**

```powershell
git add services/campaign_service/app/main.py services/campaign_service/test_context_assembler.py
git commit -m "Persist image reference attachment audit"
```

### Task 2: Expose audit metadata from the Context Viewer query

**Files:**
- Modify: `context-viewer/lib/query.ts:66-71`
- Test: `context-viewer/test/query.test.ts`

**Interfaces:**
- Consumes: `llm_generation_payloads.context_json` JSONB.
- Produces: each payload object includes `context_json.reference_audit` when present.

- [ ] **Step 1: Write the failing query test**

Add an assertion that `buildContextDetailQuery` selects `context_json` unchanged in the payload JSON object and that the query text exposes `reference_audit` only through that existing JSON field rather than selecting image payload fields.

- [ ] **Step 2: Run the focused query test**

Run from `context-viewer`:

```powershell
npm test -- --test-name-pattern="reference audit|context detail"
```

Expected: FAIL if the current query does not expose the context metadata needed by the page.

- [ ] **Step 3: Implement the minimal query change**

Keep the existing `context_json` projection and add an explicit sanitized projection inside the payload JSON object:

```sql
'reference_audit', COALESCE(lp.context_json->'reference_audit', '{}'::jsonb)
```

Do not select `reference_images`, `data`, or any image bytes.

- [ ] **Step 4: Run the focused query test**

Run the same focused command and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add context-viewer/lib/query.ts context-viewer/test/query.test.ts
git commit -m "Expose reference audit metadata to context viewer"
```

### Task 3: Render attachment verification in the viewer

**Files:**
- Modify: `context-viewer/app/page.tsx:11,120-156`
- Test: `context-viewer/test/query.test.ts` or the existing page-render tests in that file

**Interfaces:**
- Consumes: `selected.payloads[].context_json.reference_audit`.
- Produces: a safe `ReferenceAuditPanel` inside `References supplied`.

- [ ] **Step 1: Write the failing page tests**

Add page assertions for three states:

```text
Attached successfully
Selected: 2
Attached: 2
Multimodal: Yes
SHA-256
Audit unavailable for this activity
Attachment incomplete/failed
```

Use fixture metadata with `data` omitted and assert the rendered page does not include base64 content.

- [ ] **Step 2: Run the focused UI tests**

Run from `context-viewer`:

```powershell
npm test -- --test-name-pattern="reference audit|activity record detail"
```

Expected: FAIL because the panel and labels do not yet exist.

- [ ] **Step 3: Implement safe normalization**

Add a small pure helper in `context-viewer/app/page.tsx` (or a nearby helper module) that accepts unknown JSON and returns either a normalized audit or `null`. Require numeric counts and an array for failures/references; coerce display-only strings safely; ignore unknown fields and all `data` keys.

- [ ] **Step 4: Implement the panel**

Render the panel below the existing source list. Use a green success state only when counts match and failures are empty. Render per-reference rows with ID, file name, MIME type, folder, and SHA-256. Render failure rows with ID and category. For `null`, render the legacy unavailable message.

- [ ] **Step 5: Run the focused UI tests**

Run the same focused command and expect PASS.

- [ ] **Step 6: Run the full Context Viewer suite**

Run:

```powershell
npm test
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add context-viewer/app/page.tsx context-viewer/test/query.test.ts
git commit -m "Show reference attachment audit in context viewer"
```

### Task 4: Integrate, deploy, and verify

**Files:**
- Modify: deployment files only if the existing compose build does not include the changed services.

- [ ] **Step 1: Run the relevant service suites**

Run campaign-service and Context Viewer tests independently, using the commands from Tasks 1 and 3.

- [ ] **Step 2: Build and deploy**

Rebuild and restart campaign-service, context-viewer, and worker-image through the existing GCP compose deployment procedure. Do not print environment secrets.

- [ ] **Step 3: Verify service health**

Check `docker compose ps`, service startup logs, and the public Context Viewer route. Confirm the three containers are up and the route returns HTTP 200.

- [ ] **Step 4: Verify a new image activity**

Run one controlled image generation with at least one Reference, open the resulting activity in Context Viewer, and confirm the panel reports matching selected/attached counts and a SHA-256 row.

- [ ] **Step 5: Push the branch**

```powershell
git push origin feature/complete-campaign-flow
```
