# Sprint 17-19 Execution Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Sprint 17-19 optimizations for i18n engineering guardrails, locale quality consistency, and system operation observability UX.

**Architecture:** Keep current Next.js App Router structure, extend existing `lib/i18n` primitives, and enforce guardrails via ESLint + script-based CI checks. Improve System module presentation with localized operation/result mapping and severity-coded feedback.

**Tech Stack:** Next.js 16, React 19, TypeScript 5, ESLint 9.

---

## Team Split (分工)

- **Platform / Frontend Infra**: i18n key typing, lint policy, CI scripts.
- **Frontend Product UX**: locale format consistency + system operation/result UX.
- **QA / Release**: glossary + UAT checklist + lint/build signoff.

## Chunk 1: Sprint 17 - i18n 工程化

### Task 1: Type-safe i18n key access

**Files:**
- Modify: `lib/i18n/translations.ts`
- Modify: `lib/i18n/context.tsx`
- Modify: `app/campaigns/page.tsx`
- Modify: `components/workflow/workflow-board.tsx`

- [x] Add recursive `TranslationKey` type derived from locale tree.
- [x] Change `t(key)` signature from `string` to `TranslationKey`.
- [x] Refactor dynamic status key usages into typed key mappers.

### Task 2: Guardrails for hardcoded UI strings

**Files:**
- Modify: `eslint.config.mjs`
- Add: `scripts/check-i18n.mjs`
- Modify: `package.json`

- [x] Add ESLint restricted-syntax rules for JSX text and UI attributes (`placeholder`, `aria-label`, `title`).
- [x] Add heuristic script `check:i18n` for hardcoded UI text scan.
- [x] Add CI pipeline script `ci:frontend` combining i18n check + lint + build.

## Chunk 2: Sprint 18 - 語系品質

### Task 3: Locale format consistency

**Files:**
- Add: `lib/i18n/format.ts`
- Modify: `app/campaigns/page.tsx`
- Modify: `app/system/page.tsx`

- [x] Centralize date/currency formatting helpers.
- [x] Replace inline `Intl` / `toLocaleString` calls in key pages with helper functions.

### Task 4: Translation governance artifacts

**Files:**
- Add: `docs/release/i18n-glossary.md`
- Add: `docs/release/i18n-uat-checklist.md`

- [x] Define glossary for domain terms across EN / zh-Hant / ja.
- [x] Define page-by-page UAT checklist for tri-language verification.

## Chunk 3: Sprint 19 - System UX / Observability

### Task 5: Result & operation localization + severity display

**Files:**
- Modify: `app/system/page.tsx`
- Modify: `lib/i18n/translations.ts`

- [x] Localize operation token rendering (`health_check`, `purge_topic`, `retry_dlq`).
- [x] Add severity-toned operation message banner states.
- [x] Render result badges with localized labels and color semantics.

## Verification

- [x] Run: `npm run check:i18n`
- [x] Run: `npm run lint`
- [x] Run: `npm run build`
- [x] Ensure LSP diagnostics for changed files are zero
