# Reference Pack List Contrast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make created Reference Pack names and summary text visibly dark and readable on white list cards.

**Architecture:** Adjust only the existing Pack list JSX classes in `app/content-studio/page.tsx`. Keep all handlers, state, API calls, filtering, selection, deletion, and upload behavior unchanged.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS.

## Global Constraints

- Preserve selection, save, delete, filtering, and upload behavior.
- Preserve existing dark-surface contrast for the surrounding Content Studio section.
- Do not change API or data flow.

---

### Task 1: Darken created Pack list text

**Files:**
- Modify: `app/content-studio/page.tsx:617`
- Test: `npm run check:reference-pack-form`, `npx tsc --noEmit`, `npm run build`

- [ ] Add or update the focused contract to require dark classes on Pack name, active state, role, industry, and image-count summary.
- [ ] Run the focused contract before the implementation and confirm it fails if the required classes are absent.
- [ ] Apply `text-slate-900` to Pack names and `text-slate-700` to status/summary text on the white cards; retain any necessary dark-surface classes only outside the white cards.
- [ ] Run the focused contract, TypeScript check, build, and `git diff --check`.
- [ ] Commit with `fix: darken reference pack list text`.

### Task 2: Production smoke verification

**Files:** no new source files.

- [ ] Verify the frontend image is rebuilt from the commit and the frontend container is running.
- [ ] Verify `http://35.221.249.149/content-studio` returns HTTP `200`.
- [ ] Confirm no API, selection, upload, or data-flow changes in the diff.
