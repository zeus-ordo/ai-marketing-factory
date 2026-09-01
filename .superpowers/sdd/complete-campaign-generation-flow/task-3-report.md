# Task 3 Report

## Implementation

- Added `app.external_search` with a provider protocol, normalized `ExternalSearchResult`, Google Custom Search adapter, and classified errors.
- Google responses normalize `title`, `link`, `snippet`, query, provider, and UTC retrieval time. API keys are never included in error messages.
- Added `EXTERNAL_SEARCH_PROVIDER`, `EXTERNAL_SEARCH_API_KEY`, and `EXTERNAL_SEARCH_ENGINE_ID` wiring without storing values in source or `.env` files.
- Added `build_external_search_query` and `search_campaign_external_context` as the generation-context integration seam. Intentionally disabled search remains internal-only; Task 4 can add configured results to its snapshot without changing campaign APIs.

## Verification

- Focused adapter tests cover normalization, quota, provider failure, timeout, secret redaction, and incomplete configuration.
- `httpx` was added because it was not present in campaign service requirements.

## Review Fixes

- Sanitized provider errors now suppress exception chaining with `from None`, preventing upstream request URLs and query parameters from appearing in causes or tracebacks.
- Google provider configuration with a missing API key or engine ID now raises `ExternalSearchError` with code `not_configured`. Empty, `disabled`, `none`, and `off` provider values remain explicit opt-outs returning `None`.
- Added regression tests for exception causes, representations, traceback text, and incomplete configuration classification.
