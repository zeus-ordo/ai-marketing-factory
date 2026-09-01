# Task 3 Report

## Implementation

- Added `app.external_search` with a provider protocol, normalized `ExternalSearchResult`, Google Custom Search adapter, and classified errors.
- Google responses normalize `title`, `link`, `snippet`, query, provider, and UTC retrieval time. API keys are never included in error messages.
- Added `EXTERNAL_SEARCH_PROVIDER`, `EXTERNAL_SEARCH_API_KEY`, and `EXTERNAL_SEARCH_ENGINE_ID` wiring without storing values in source or `.env` files.
- Added `build_external_search_query` and `search_campaign_external_context` as the generation-context integration seam. It returns internal-only behavior when search is not configured; Task 4 can add the returned results to its snapshot without changing campaign APIs.

## Verification

- Focused adapter tests cover normalization, quota, provider failure, timeout, secret redaction, and incomplete configuration.
- `httpx` was added because it was not present in campaign service requirements.
