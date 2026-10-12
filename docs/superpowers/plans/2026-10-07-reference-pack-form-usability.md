# Reference Pack Form Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label every Reference Pack filter, editor, and upload control and make all entered values readable.

**Architecture:** Keep the existing Content Studio state and API flow. Add localized visible labels and `htmlFor`/`id` associations directly around the existing controls, then apply a consistent text-color class to inputs, selects, options, and upload status text.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, existing `useI18n` translations.

## Global Constraints

- Preserve existing API calls, validation, upload limits, analysis states, and localization architecture.
- Add translations for all new labels in every supported locale.
- Do not change Reference Pack selection, saving, or upload behavior.
- Use dark text for entered values and readable placeholder text on the white form.

---

### Task 1: Add localized labels and accessible associations

**Files:**
- Modify: `app/content-studio/page.tsx:609-623`
- Modify: `lib/i18n/translations.ts` under each `referencePacks` locale section
- Test: Content Studio UI contract or `npm run check:i18n`

- [ ] Add translation keys for filter labels, Pack field labels, active state, choose/selected/upload labels, and the no-selected-Pack upload guidance.
- [ ] Run `npm run check:i18n` before the JSX conversion to record the current detection failure.
- [ ] Add visible labels for role filter, industry filter, active filter, Pack name, role, industry, selection mode, maximum images, priority, active checkbox, choose images, selected files, and upload action.
- [ ] Add stable `id` attributes and matching `htmlFor` values to every input/select/file input label.
- [ ] Add explicit guidance in the upload area when `selectedPackId` is empty; keep upload controls rendered only for a selected Pack.
- [ ] Run `npm run check:i18n` and the existing Content Studio tests; require no hardcoded UI text findings.
- [ ] Commit with `fix: label reference pack upload fields`.

### Task 2: Make Content Studio text readable

**Files:**
- Modify: `app/content-studio/page.tsx:609-623`
- Test: frontend build and Content Studio UI checks

- [ ] Apply `text-slate-900` and `dark:text-slate-100` to text inputs, selects, textareas, and select options where supported.
- [ ] Apply `placeholder:text-slate-400` to text inputs and textareas.
- [ ] Apply explicit readable text classes to filter controls, file selection status, upload statuses, and no-Pack guidance.
- [ ] Preserve disabled and focus styles; do not alter form values or event handlers.
- [ ] Run `npm run build` and verify the Content Studio route compiles successfully.
- [ ] Commit with `fix: improve reference pack form contrast`.

### Task 3: Run focused and release verification

**Files:** no new source files.

- [ ] Run the frontend unit/contract tests covering Content Studio and upload behavior.
- [ ] Run `npm run check:i18n`.
- [ ] Run `npm run build`.
- [ ] Run `git diff --check`.
- [ ] Inspect `git status --short` and confirm only reviewed UI, translation, and documentation files are changed.
- [ ] Deploy the frontend only after local checks pass, then verify the Content Studio route returns HTTP 200.
