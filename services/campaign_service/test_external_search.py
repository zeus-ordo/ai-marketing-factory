from datetime import datetime, timezone
import traceback

import httpx
import pytest

from app.external_search import (
    ExternalSearchError,
    GoogleCustomSearchProvider,
    build_campaign_search_query,
    build_search_provider,
)


def test_google_provider_normalizes_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "key"
        assert request.url.params["cx"] == "engine"
        assert request.url.params["q"] == "新品調酒 餐酒館 awareness"
        assert request.url.params["num"] == "3"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "Cocktail source",
                        "link": "https://example.com/source",
                        "snippet": "Useful campaign context",
                    }
                ]
            },
        )

    provider = GoogleCustomSearchProvider(
        "key", "engine", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    results = provider.search("新品調酒 餐酒館 awareness", 3)

    assert results[0].source_type == "external_web"
    assert results[0].title == "Cocktail source"
    assert results[0].url == "https://example.com/source"
    assert results[0].summary == "Useful campaign context"
    assert results[0].query == "新品調酒 餐酒館 awareness"
    assert results[0].provider == "google"
    assert results[0].retrieved_at.tzinfo == timezone.utc


@pytest.mark.parametrize(
    ("response", "category"),
    [
        (httpx.Response(429), "quota"),
        (httpx.Response(500), "provider_error"),
    ],
)
def test_http_failures_are_classified_without_secret_leak(response: httpx.Response, category: str):
    provider = GoogleCustomSearchProvider(
        "secret-key",
        "engine",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: response)),
    )

    with pytest.raises(ExternalSearchError) as exc:
        provider.search("query", 3)

    assert exc.value.category == category
    assert "secret-key" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert "secret-key" not in repr(exc.value)
    assert "secret-key" not in "".join(traceback.format_exception(exc.value))


def test_timeout_is_classified_without_secret_leak():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out", request=request)

    provider = GoogleCustomSearchProvider(
        "secret-key",
        "engine",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ExternalSearchError) as exc:
        provider.search("query", 3)

    assert exc.value.category == "timeout"
    assert "secret-key" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert "secret-key" not in repr(exc.value)
    assert "secret-key" not in "".join(traceback.format_exception(exc.value))


def test_incomplete_configuration_is_not_configured():
    for settings in (
        {"EXTERNAL_SEARCH_PROVIDER": "google"},
        {"EXTERNAL_SEARCH_PROVIDER": "google", "EXTERNAL_SEARCH_API_KEY": "key"},
    ):
        with pytest.raises(ExternalSearchError) as exc:
            build_search_provider(settings)
        assert exc.value.category == "not_configured"
        assert exc.value.code == "not_configured"


def test_disabled_provider_is_explicit_and_backward_compatible():
    assert build_search_provider({"EXTERNAL_SEARCH_PROVIDER": "disabled"}) is None


def test_campaign_search_query_uses_only_campaign_fields():
    assert build_campaign_search_query("New drink", "Restaurant", "awareness") == "New drink Restaurant awareness"
    assert build_campaign_search_query("  New drink ", "", " awareness ") == "New drink awareness"
