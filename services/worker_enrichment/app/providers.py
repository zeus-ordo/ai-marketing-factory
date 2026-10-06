import base64
import json
import math
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from .safe_attributes import validate_safe_attributes as _campaign_validate_attributes


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
        except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError) as exc:
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
        except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderError("EMBEDDING_PROVIDER_ERROR") from exc


GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_ANALYSIS_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


def _response_text(payload: dict[str, Any]) -> str:
    parts = payload["candidates"][0]["content"]["parts"]
    text = "".join(part["text"] for part in parts if isinstance(part.get("text"), str))
    if not text:
        raise ValueError("missing provider response text")
    return text


def _parse_json_response(text: str) -> Any:
    fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.IGNORECASE | re.DOTALL)
    return json.loads(fenced.group(1) if fenced else text)


def _gemini_model_path(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


class GeminiImageAnalysisProvider(ImageAnalysisProvider):
    def __init__(self, api_key: str, model: str, base_url: str = GEMINI_API_BASE_URL) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def analyze(self, image_path: str, mime_type: str, title: str, description: str) -> dict[str, Any]:
        try:
            if not self.api_key:
                raise ProviderError("ANALYSIS_PROVIDER_ERROR")
            image_data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            prompt = (
                "Analyze this image and return only a JSON object of useful visual attributes. "
                "Do not include image bytes, paths, URLs, or private metadata.\n"
                f"Title: {title}\nDescription: {description}"
            )
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/{_gemini_model_path(self.model)}:generateContent",
                    headers={"x-goog-api-key": self.api_key},
                    json={
                        "contents": [{"parts": [
                            {"inlineData": {"mimeType": mime_type, "data": image_data}},
                            {"text": prompt},
                        ]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "responseSchema": {"type": "OBJECT"},
                        },
                    },
                )
                response.raise_for_status()
                attributes = _parse_json_response(_response_text(response.json()))
                return validate_attributes(attributes)
        except Exception as exc:
            raise ProviderError("ANALYSIS_PROVIDER_ERROR") from exc


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str, base_url: str = GEMINI_API_BASE_URL) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, text: str) -> list[float]:
        try:
            if not self.api_key:
                raise ProviderError("EMBEDDING_PROVIDER_ERROR")
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/{_gemini_model_path(self.model)}:embedContent",
                    headers={"x-goog-api-key": self.api_key},
                    json={"content": {"parts": [{"text": text}]}},
                )
                response.raise_for_status()
                return validate_embedding(response.json()["embedding"]["values"])
        except Exception as exc:
            raise ProviderError("EMBEDDING_PROVIDER_ERROR") from exc


def _use_gemini(provider_variable: str) -> bool:
    configured = os.getenv(provider_variable, "").strip().lower()
    if configured:
        return configured == "gemini"
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def build_providers() -> tuple[ImageAnalysisProvider, EmbeddingProvider]:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    analysis_model = os.getenv("GEMINI_ANALYSIS_MODEL", DEFAULT_GEMINI_ANALYSIS_MODEL).strip()
    embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL).strip()
    gemini_base_url = os.getenv("GEMINI_API_BASE_URL", GEMINI_API_BASE_URL).strip().rstrip("/")

    analysis: ImageAnalysisProvider
    if _use_gemini("IMAGE_ANALYSIS_PROVIDER"):
        analysis = GeminiImageAnalysisProvider(gemini_key, analysis_model, gemini_base_url)
    else:
        analysis = HttpImageAnalysisProvider(
            os.getenv("IMAGE_ANALYSIS_BASE_URL", "http://multimodal-provider:8080"),
            os.getenv("IMAGE_ANALYSIS_MODEL", "vision-model"),
            os.getenv("IMAGE_ANALYSIS_API_KEY", ""),
        )

    embedding: EmbeddingProvider
    if _use_gemini("EMBEDDING_PROVIDER"):
        embedding = GeminiEmbeddingProvider(gemini_key, embedding_model, gemini_base_url)
    else:
        embedding = HttpEmbeddingProvider(
            os.getenv("EMBEDDING_BASE_URL", "http://embedding-provider:8080"),
            os.getenv("EMBEDDING_MODEL", "embedding-model"),
            os.getenv("EMBEDDING_API_KEY", ""),
        )
    return analysis, embedding


analysis_provider, embedding_provider = build_providers()
