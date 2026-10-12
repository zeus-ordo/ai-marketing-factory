# Quality Checks Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make lint, i18n, and secret checks pass without weakening production security or changing runtime behavior.

**Architecture:** Keep checks strict for tracked source and production configuration. Adjust only scan boundaries for generated output, untracked local environments, and explicitly marked test fixtures. Move remaining customer-facing hardcoded copy into the existing translation dictionary and use the existing `useI18n` accessor.

**Tech Stack:** Next.js 16, React 19, TypeScript, ESLint flat config, Node check scripts, existing `lib/i18n/translations.ts`, pytest.

## Global Constraints

- Keep the existing no-hardcoded-UI-copy ESLint rule enabled.
- Do not add real credentials, API keys, passwords, or DSNs to tracked files.
- Do not change production API, authentication, image quota, or deployment behavior.
- Do not suppress lint errors with broad `eslint-disable` directives.
- Preserve the current Chinese UI wording when converting it to translation keys.

---

### Task 1: Make ESLint scan only source files

**Files:** `eslint.config.mjs`, `context-viewer/app/page.tsx`, `context-viewer/lib/query.ts`.

- [ ] Reproduce the current failure with `npm run lint`; record generated `.next` errors and source hook/type errors.
- [ ] Add precise global ignores for `**/.next/**`, `**/out/**`, `**/build/**`, `**/coverage/**`, and `next-env.d.ts`, without ignoring application source.
- [ ] Fix Context Viewer source hook errors while preserving URL filter restoration and selected-row cleanup.
- [ ] Replace `any` in `context-viewer/lib/query.ts` with existing row types or `unknown` narrowed at the database boundary; do not alter SQL or returned fields.
- [ ] Run `npm run lint` and require exit 0.
- [ ] Commit with `chore: scope lint to source files`.

### Task 2: Remove hardcoded campaign UI copy

**Files:** `app/campaigns/page.tsx:2030-2166`, `lib/i18n/translations.ts`.

- [ ] Add translation keys for edit objectives, platform labels, edit labels/placeholders, asset table copy, and regeneration dialog copy under `campaigns.edit.*` and `campaigns.regenerate.*` in every locale required by `TranslationKey`.
- [ ] Add failing or detection-focused coverage by running `npm run check:i18n` before replacing strings.
- [ ] Replace every detected JSX text, placeholder, title, and aria label with `t("...")`; keep machine values such as `awareness`, `engagement`, and `conversion` unchanged.
- [ ] Run `npm run check:i18n` and require the OK message.
- [ ] Commit with `fix: localize campaign edit copy`.

### Task 3: Make secret scanning release-accurate

**Files:** `scripts/check-secrets.mjs`, `scripts/check-secrets.test.mjs`.

- [ ] Add `scripts/check-secrets.test.mjs` tests proving untracked `.env.local`/`.env.test.local` are not release inputs, while tracked production config containing a credential-shaped literal remains rejected.
- [ ] Run the focused scanner tests and confirm they fail against the current unconditional local-env inclusion.
- [ ] Change `trackedConfigEntries()` so local env files are included only when Git reports them tracked, or when `CHECK_LOCAL_ENV=1` is explicitly supplied.
- [ ] Preserve all tracked config, DSN, token, password, and API-key detection.
- [ ] Run `npm run check:secrets` and require `[secrets] PASS`.
- [ ] Commit with `fix: scope secret scan to release files`.

### Task 4: Run the complete quality gate

**Files:** no new source files.

- [ ] Run campaign service, worker image, orchestrator, and worker enrichment pytest suites separately with their own `PYTHONPATH` values.
- [ ] In `context-viewer`, run `npm test` and `npm run build`.
- [ ] From the root, run `npm run lint`, `npm run check:i18n`, `npm run check:secrets`, `npm run build`, and `git diff --check`.
- [ ] Inspect `git status --short`; ensure no `.env*`, generated output, test password, or temporary files are staged.
- [ ] Commit any reviewed final adjustment with `chore: pass release quality checks`.
