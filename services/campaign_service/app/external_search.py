from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

import httpx


@dataclass(frozen=True)
class ExternalSearchResult:
    source_type: Literal["external_web"]
    title: str
    url: str
    summary: str
    retrieved_at: datetime
    query: str
    provider: str


class SearchProvider(Protocol):
    def search(self, query: str, limit: int) -> list[ExternalSearchResult]: ...


class ExternalSearchError(RuntimeError):
    def __init__(self, category: Literal["quota", "rate_limit", "timeout", "provider_error", "not_configured"], message: str):
        self.category = category
        super().__init__(message)


def build_campaign_search_query(product_name: str, industry_category: str, objective: str) -> str:
    return " ".join(value.strip() for value in (product_name, industry_category, objective) if value.strip())


class GoogleCustomSearchProvider:
    def __init__(
        self,
        api_key: str,
        engine_id: str,
        base_url: str = "https://www.googleapis.com/customsearch/v1",
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key
        self._engine_id = engine_id
        self._base_url = base_url
        self._client = client or httpx.Client(timeout=15.0)

    def search(self, query: str, limit: int) -> list[ExternalSearchResult]:
        try:
            response = self._client.get(
                self._base_url,
                params={"key": self._api_key, "cx": self._engine_id, "q": query, "num": max(1, min(limit, 10))},
            )
            if response.status_code == 429:
                raise ExternalSearchError("quota", "External search quota exceeded")
            response.raise_for_status()
            payload = response.json()
        except ExternalSearchError:
            raise
        except httpx.TimeoutException as exc:
            raise ExternalSearchError("timeout", "External search timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise ExternalSearchError("provider_error", "External search provider failed") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalSearchError("provider_error", "External search provider returned an invalid response") from exc

        retrieved_at = datetime.now(timezone.utc)
        return [
            ExternalSearchResult(
                source_type="external_web",
                title=str(item.get("title", "")),
                url=str(item.get("link", "")),
                summary=str(item.get("snippet", "")),
                retrieved_at=retrieved_at,
                query=query,
                provider="google",
            )
            for item in payload.get("items", [])[: max(0, limit)]
            if isinstance(item, dict)
        ]


def _setting(settings: Any, name: str, default: str = "") -> str:
    if isinstance(settings, dict):
        return str(settings.get(name, default) or "").strip()
    return str(getattr(settings, name, default) or "").strip()


def build_search_provider(settings: Any) -> SearchProvider | None:
    provider = _setting(settings, "EXTERNAL_SEARCH_PROVIDER").lower()
    api_key = _setting(settings, "EXTERNAL_SEARCH_API_KEY")
    engine_id = _setting(settings, "EXTERNAL_SEARCH_ENGINE_ID")
    if provider != "google" or not api_key or not engine_id:
        return None
    return GoogleCustomSearchProvider(api_key=api_key, engine_id=engine_id)
