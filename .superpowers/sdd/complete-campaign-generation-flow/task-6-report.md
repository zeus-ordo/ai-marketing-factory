# Task 6 Report

Implemented additive generation diagnostics and single-task retry visibility.

- Campaign API responses now optionally include generation context ID, source counts, token counts/ratios, selected reference IDs, matched folders, external URLs, and sanitized source provenance.
- Campaign tasks expose retry count, failure category/detail, blocked reason, next retry time, provider/model, and generation context ID.
- Review responses and the Review Center expose generation context/source provenance and task failure diagnostics.
- Added Traditional Chinese, English, and Japanese labels for diagnostics, retryability, attempts, and retry states.
- Added a JWT-authorized, company-scoped path to the existing single-task retry operation. The UI retries only the selected failed task and does not independently retry descendants.
- Added loading/empty/error behavior through the existing page and table states; diagnostics are responsive and use accessible section labels and buttons.
- Provenance serialization excludes source text and credentials.

Verification:

- `node scripts/test-campaign-flow-contract.mjs`: passed
- `python -m pytest services/campaign_service -q`: 47 passed
- `npm run build`: passed
- `git diff --check`: passed

The build retains existing warnings about FastAPI `on_event` deprecation and multiple lockfiles/workspace-root inference.
