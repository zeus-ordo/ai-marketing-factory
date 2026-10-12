# Hide Regenerate After Submit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide the regenerate action for an Asset after a regeneration request succeeds, while preserving retry behavior on failure.

**Architecture:** Add a local `Set<string>` of successfully submitted Asset IDs to the Campaign edit screen. Include the set in the existing render condition for the regenerate button, add the ID only after `regenerateAsset` resolves, and leave it unchanged on errors.

**Tech Stack:** Next.js 16, React 19, TypeScript, existing campaign UI contract checks.

## Global Constraints

- Keep the existing modal, validation, API payload, loading state, and new-asset review flow unchanged.
- Do not change backend behavior or data contracts.
- A failed regeneration request must leave the action available for retry.

---

### Task 1: Hide successful regeneration actions

**Files:**
- Modify: `app/campaigns/page.tsx:262,997-1024,2103-2111`
- Modify: focused campaign UI contract script/test
- Test: focused contract, TypeScript, frontend build

- [ ] Add a failing contract assertion showing a successfully submitted Asset ID is excluded from the regenerate-action condition.
- [ ] Run the focused contract and confirm it fails before implementation.
- [ ] Add `regenerateSubmittedAssetIds` state as `useState<Set<string>>`.
- [ ] Add `regenerateTarget.id` to a copied Set only after `regenerateAsset(...)` succeeds.
- [ ] Update the render condition to require that the Asset ID is not in the submitted set.
- [ ] Do not add the ID in the catch path; preserve retry behavior.
- [ ] Run focused contract, `npx tsc --noEmit`, `npm run build`, and `git diff --check`.
- [ ] Commit with `fix: hide regenerate action after submit`.

### Task 2: Verify production frontend

**Files:** no new source files.

- [ ] Push the feature branch containing the fix.
- [ ] Rebuild and recreate only frontend with `deploy/docker-compose.gcp.yml`.
- [ ] Verify the frontend container is running and `/content-studio` and `/campaigns` return HTTP `200`.
- [ ] Confirm no backend/API/data contract changes in the diff.
