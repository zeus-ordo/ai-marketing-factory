# Task 3 Review Report

## Status

- Spec compliance: **FAIL**
- Task quality: **FAIL**
- Reviewed range: `2b6016d..673eb4e`
- Commit: `673eb4e feat: allow text files in reference pack UI`

## Findings

### Critical

- None found.

### Important

1. **Frontend text classifier does not match the backend classifier.**
   - File: `app/content-studio/page.tsx:42-45`
   - The frontend accepts only an empty MIME, `text/plain`, or `text/markdown`. The backend also accepts `.txt` and `.md` with `application/octet-stream` (`services/campaign_service/app/main.py:6675-6683`). A valid compatible browser upload is therefore marked `UNSUPPORTED_FILE_TYPE` client-side.
   - Fix: include `application/octet-stream` in the frontend text classifier while retaining the extension/MIME pairing rules.

2. **Image-only labels remain visible for the text-capable control.**
   - Files: `lib/i18n/translations.ts` Reference Pack entries; `app/content-studio/page.tsx:667`
   - `noFiles` remains image-specific in all three locales. Upload success/failure and item deletion strings also still say images. The new neutral labels are applied through an imperative DOM effect while the JSX still renders the old image labels, which can be overwritten by later React reconciliation.
   - Fix: render the neutral translation keys directly in JSX and update the visible empty/status/action labels to neutral file wording in all three locales.

3. **The contract test can pass while the actual input remains image-only.**
   - File: `scripts/check-reference-pack-form-contract.mjs:44-53`
   - It checks for a constant and helper-name occurrences, but the JSX input still declares the old image-only `accept` value and old image-only `onChange` handler. It also does not test `application/octet-stream` or the neutral empty/status labels.
   - Fix: assert the actual input `accept`/selection path and add compatible-MIME and neutral-label coverage.

### Minor

- `referencePacks.fileMetadata` is added in all three locales but unused (`lib/i18n/translations.ts`; `app/content-studio/page.tsx:650`). Text metadata is rendered as raw type plus rounded KB without the translated metadata label.
- The text item is neutral and bypasses `ImageAnalysisSummary` in the analysis-items row, but the separate item list still gives every item a generic preview action rather than a dedicated text/file indicator.

## Requirement Verification

- `.txt`/`.md` and existing PNG/JPEG/WebP/GIF formats in intended accept constant: **PASS**.
- Frontend classifier matches backend: **FAIL** due to missing `application/octet-stream`.
- Text rows avoid image-analysis rendering and show filename/type/size metadata: **PASS**, with the consistency concern above.
- Existing image preview, analysis, retry, concurrency, and batch merging remain present: **PASS by diff inspection**.
- All three locales contain supported-format and text-item labels: **PASS**. All visible labels are neutral: **FAIL**.
- No backend/RAG files changed in the reviewed range: **PASS**. Only the page, translations, and frontend contract test changed.
- No private storage paths, raw bytes, or base64 introduced: **PASS**.

## Verification

- `node scripts/check-reference-pack-form-contract.mjs`: **PASS**
- `npm run build`: **PASS** (production build and TypeScript completed)
- `git diff --check 2b6016d..673eb4e`: **PASS**
- `npm run lint`: **FAIL**, with repository/generated `context-viewer` errors and warnings; no Task 3-specific error isolated.
- `npm run check:i18n`: **FAIL**, reporting existing hardcoded strings in `app/campaigns/page.tsx`; no Content Studio finding reported.

## Assessment

The diff preserves the existing image upload API and workflow and passes the focused test/build, but it does not satisfy the explicit classifier-match and neutral-label requirements. Fix the Important issues and strengthen the contract test before marking Task 3 complete.

## Fix Report

Addressed all review findings in the current worktree.

- Added `application/octet-stream` to the `.txt`/`.md` frontend classifier.
- Replaced imperative DOM mutation with direct JSX for the actual accept value, selection handler, neutral file labels, status/delete copy, and text metadata.
- Added neutral English, Traditional Chinese, and Japanese labels for empty, success, failure, delete, and pack-selection states.
- Strengthened the contract to inspect the actual input accept value and selection handler, require octet-stream support, require neutral labels in all locales, and reject the old image-only JSX calls.
- Preserved image handling, retry, concurrency, batch state merging, and API usage. No backend or RAG files changed.

### Verification

- Command: `node scripts/check-reference-pack-form-contract.mjs`
- Output: `[check:reference-pack-form] OK`
- Command: `npm run build`
- Output: `Compiled successfully`; TypeScript completed; 26/26 static pages generated.
- Command: `git diff --check`
- Output: passed with no whitespace errors.
