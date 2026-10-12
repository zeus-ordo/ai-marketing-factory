# Reference Pack Form Usability Design

## Goal

Make the complete Reference Pack creation and image upload flow understandable
to non-technical users by labeling every control and ensuring entered text is
readable.

## Design

- Add visible labels and accessible `id`/`htmlFor` associations for the three
  list filters: role, industry, and active status.
- Add visible labels for every Pack editor control: name, role, industry,
  selection mode, maximum images, priority, active state, choose images,
  selected files, and upload action.
- Keep the existing save-then-select-Pack workflow, but make the upload area
  state explicit when no Pack is selected.
- Use dark slate text for input/select values, lighter slate text for
  placeholders, and black/dark text for select options on the white form.
- Preserve existing API calls, validation, upload limits, analysis states, and
  localization architecture. Add translations for all new labels in every
  supported locale.

## Verification

- Content Studio component tests cover labels, accessible associations, and
  visible upload guidance.
- `npm run check:i18n` reports no hardcoded UI text.
- Root and Context Viewer builds pass.
- Existing campaign and upload test suites pass.
- `git diff --check` passes.
