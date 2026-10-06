import base64
import math
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

try:
    from services.shared.image_enrichment import validate_safe_attributes as _campaign_validate_attributes
except ImportError:
    from shared.image_enrichment import validate_safe_attributes as _campaign_validate_attributes


class ProviderError(RuntimeError):
    """Safe error classification for retryable provider failures."""

    def __init__(self, code: str = "PROVIDER_ERROR") -> None:
        self.code = code
        super().__init__(code)


class ImageAnalysisProvider(ABC):
    @abstractmethod
    def analyze(self, image_path: str, mime_type: str, title: str, description: str) -> dict[str, Any]:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


def validate_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return _campaign_validate_attributes(attributes)


def validate_embedding(embedding: list[float]) -> list[float]:
    if not isinstance(embedding, list) or not embedding:
        raise ValueError("embedding must be a non-empty list")
    result = [float(value) for value in embedding]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("embedding must contain finite numbers")
    return result


class HttpImageAnalysisProvider(ImageAnalysisProvider):
    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def analyze(self, image_path: str, mime_type: str, title: str, description: str) -> dict[str, Any]:
        try:
            image_data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/analyze",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "image_data": image_data, "mime_type": mime_type, "title": title, "description": description},
                )
                response.raise_for_status()
                return validate_attributes(response.json())
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise ProviderError("ANALYSIS_PROVIDER_ERROR") from exc


class HttpEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, text: str) -> list[float]:
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": text},
                )
                response.raise_for_status()
                return validate_embedding(response.json()["data"][0]["embedding"])
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderError("EMBEDDING_PROVIDER_ERROR") from exc


analysis_provider: ImageAnalysisProvider = HttpImageAnalysisProvider(
    os.getenv("IMAGE_ANALYSIS_BASE_URL", "http://multimodal-provider:8080"),
    os.getenv("IMAGE_ANALYSIS_MODEL", "vision-model"),
    os.getenv("IMAGE_ANALYSIS_API_KEY", ""),
)
embedding_provider: EmbeddingProvider = HttpEmbeddingProvider(
    os.getenv("EMBEDDING_BASE_URL", "http://embedding-provider:8080"),
    os.getenv("EMBEDDING_MODEL", "embedding-model"),
    os.getenv("EMBEDDING_API_KEY", ""),
)
