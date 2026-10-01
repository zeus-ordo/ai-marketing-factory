# Complete Diagnostics Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Task 6 P1 worker validation, diagnostics presentation, and retry-action safety.

**Architecture:** Keep worker contract validation at the image worker schema and endpoint boundary. Reuse the campaign API diagnostics shape, adding small presentation helpers for sanitized provenance URLs and retry eligibility so Campaign and Review render identical safe data.

**Tech Stack:** FastAPI/Pydantic, React/Next.js, TypeScript, pytest, project frontend test tooling.

## Global Constraints

- Only `http` and `https` provenance URLs may render as links.
- Retry is rendered only when `task.retryable === true` and `task.retry_count < max attempts`.
- Preserve responsive and accessible existing UI patterns.
- Sanitize external URLs and error details before presentation.

---

### Task 1: Image Regeneration Contract

**Files:**
- Modify: `services/worker_image/app/schemas.py`
- Modify: `services/campaign_service/app/main.py`
- Test: `services/campaign_service/test_context_assembler.py`

- [ ] Add required `company_id: str` to `RevisionRequest`.
- [ ] Validate the actual regeneration payload with `ImageRunRequest`/`RevisionRequest` and assert successful saved metadata.
- [ ] Run the focused image regeneration tests.

### Task 2: Diagnostics Presentation

**Files:**
- Modify: `app/campaigns/page.tsx`
- Modify: `components/review/review-queue-table.tsx`
- Modify: `lib/api/campaigns.ts` if transform types require it
- Test: existing frontend test location discovered from package scripts

- [ ] Add a pure presentation transform/helper for provenance fields, sanitized URL eligibility, provider/model, and sanitized error detail.
- [ ] Render provenance source type, label, folder, and safe external URL in Campaign and Review views.
- [ ] Render task provider/model and sanitized error detail while retaining source summaries and ratios.
- [ ] Add transform/UI assertions for safe links and text-only unsafe URLs.

### Task 3: Retry Eligibility

**Files:**
- Modify: `app/campaigns/page.tsx`
- Test: frontend test location discovered from package scripts

- [ ] Add a retry eligibility assertion for retryable non-exhausted tasks.
- [ ] Hide Retry for non-retryable and exhausted tasks.
- [ ] Preserve keyboard/accessibility behavior.

### Task 4: Verification and Report

**Files:**
- Modify: `.superpowers/sdd/complete-campaign-generation-flow/task-6-report.md`

- [ ] Run focused/all campaign, orchestrator, and worker tests.
- [ ] Run the campaign-flow contract, `git diff --check`, and `npm run build`.
- [ ] Append verification results and commit as `Complete diagnostics presentation`.
