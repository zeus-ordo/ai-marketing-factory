# Quality Checks Cleanup Design

## Goal

Make the repository's release-quality checks accurately report source quality
without treating generated build output, local untracked environments, or
explicit test fixtures as production defects.

## Scope

### ESLint

- Ignore generated output such as `.next`, build, and coverage directories.
- Keep the existing no-hardcoded-UI-copy rule enabled for application source.
- Fix actual source lint errors rather than disabling the rules.
- Keep generated Context Viewer output outside the root lint traversal.

### i18n

- Replace hardcoded customer-facing JSX text and UI attributes in
  `app/campaigns/page.tsx` with existing translation accessors.
- Add only the required translation keys to the existing locale dictionaries.
- Preserve current rendered copy and behavior.

### Secret scan

- Continue scanning tracked configuration and source files.
- Do not classify untracked local environment files as release contents.
- Treat clearly marked test fixtures and fake credentials as test data, while
  continuing to reject credential-shaped values in tracked production config.
- Do not weaken detection for real DSNs, tokens, passwords, or API keys.

## Verification

The following must exit successfully:

```text
npm run lint
npm run check:i18n
npm run check:secrets
python -m pytest -q services/campaign_service
python -m pytest -q services/worker_image
npm test (context-viewer)
npm run build
npm run build (context-viewer)
git diff --check
```

No production API behavior, authentication behavior, image quota behavior, or
deployment configuration should change as part of this cleanup.
