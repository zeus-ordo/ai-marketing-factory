import math

import pytest

from app import providers
from app.providers import EmbeddingProvider, ImageAnalysisProvider, ProviderError, validate_embedding, validate_attributes
from app.safe_attributes import validate_safe_attributes


def test_provider_interfaces_expose_required_methods():
    assert callable(getattr(ImageAnalysisProvider, "analyze"))
    assert callable(getattr(EmbeddingProvider, "embed"))


def test_analysis_attributes_are_json_only_and_reject_private_values():
    assert validate_attributes({"objects": ["bowl"], "confidence": 0.9}) == {
        "objects": ["bowl"],
        "confidence": 0.9,
    }

    with pytest.raises(ValueError):
        validate_attributes({"stored_path": "/private/image.png"})


def test_embedding_must_be_finite_numbers():
    assert validate_embedding([0.1, -2, 3.5]) == [0.1, -2.0, 3.5]
    with pytest.raises(ValueError):
        validate_embedding([math.nan])


@pytest.mark.parametrize(
    "attributes",
    [
        {"path": "../../secret.png"},
        {"relative": "../secret.png"},
        {"payload": "data:image/png;base64,AAAA"},
        {"binary_data": "AA=="},
    ],
)
def test_standalone_runtime_validator_rejects_private_path_and_binary_values(monkeypatch, attributes):
    monkeypatch.setattr(providers, "_campaign_validate_attributes", validate_safe_attributes)

    with pytest.raises((TypeError, ValueError)):
        providers.validate_attributes(attributes)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise providers.httpx.HTTPStatusError("provider failed", request=None, response=None)

    def json(self):
        return self.payload


class FakeClient:
    response = None
    calls = []

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_gemini_image_analysis_sends_inline_image_and_parses_fenced_json(monkeypatch, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"png-bytes")
    client = FakeClient
    client.calls = []
    client.response = FakeResponse({
        "candidates": [{"content": {"parts": [{"text": "```json\n{\"objects\":[\"bowl\"]}\n```"}]}}]
    })
    monkeypatch.setattr(providers.httpx, "Client", client)

    result = providers.GeminiImageAnalysisProvider("test-key", "gemini-test").analyze(
        str(image), "image/png", "Lunch", "A bowl on a table"
    )

    assert result == {"objects": ["bowl"]}
    url, kwargs = client.calls[0]
    assert url.endswith("/v1beta/models/gemini-test:generateContent")
    assert kwargs["headers"] == {"x-goog-api-key": "test-key"}
    assert kwargs["json"]["contents"][0]["parts"][0]["inlineData"]["data"]
    assert "Lunch" in kwargs["json"]["contents"][0]["parts"][1]["text"]
    assert kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_image_analysis_rejects_malformed_json_as_safe_provider_error(monkeypatch, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"png-bytes")
    FakeClient.calls = []
    FakeClient.response = FakeResponse({"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]})
    monkeypatch.setattr(providers.httpx, "Client", FakeClient)

    with pytest.raises(ProviderError) as error:
        providers.GeminiImageAnalysisProvider("secret-key", "gemini-test").analyze(
            str(image), "image/png", "", ""
        )

    assert str(error.value) == "ANALYSIS_PROVIDER_ERROR"
    assert "secret-key" not in str(error.value)


def test_gemini_embedding_sends_canonical_text_and_parses_values(monkeypatch):
    FakeClient.calls = []
    FakeClient.response = FakeResponse({"embedding": {"values": [0.1, -0.2]}})
    monkeypatch.setattr(providers.httpx, "Client", FakeClient)

    result = providers.GeminiEmbeddingProvider("secret-key", "gemini-embedding-test").embed('{"objects":["bowl"]}')

    assert result == [0.1, -0.2]
    url, kwargs = FakeClient.calls[0]
    assert url.endswith("/v1beta/models/gemini-embedding-test:embedContent")
    assert kwargs["headers"] == {"x-goog-api-key": "secret-key"}
    assert kwargs["json"] == {"content": {"parts": [{"text": '{"objects":["bowl"]}'}]}}


def test_gemini_embedding_rejects_malformed_response_as_safe_provider_error(monkeypatch):
    FakeClient.calls = []
    FakeClient.response = FakeResponse({"embedding": {"values": ["not-a-number"]}})
    monkeypatch.setattr(providers.httpx, "Client", FakeClient)

    with pytest.raises(ProviderError) as error:
        providers.GeminiEmbeddingProvider("secret-key", "gemini-embedding-test").embed("attributes")

    assert str(error.value) == "EMBEDDING_PROVIDER_ERROR"
    assert "secret-key" not in str(error.value)


def test_gemini_timeout_is_redacted_provider_error(monkeypatch, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"png-bytes")
    FakeClient.calls = []
    FakeClient.response = TimeoutError("secret-key /private/image.png")
    monkeypatch.setattr(providers.httpx, "Client", FakeClient)

    with pytest.raises(ProviderError) as error:
        providers.GeminiImageAnalysisProvider("secret-key", "gemini-test").analyze(
            str(image), "image/png", "", ""
        )

    assert str(error.value) == "ANALYSIS_PROVIDER_ERROR"
    assert "secret-key" not in str(error.value)
    assert "/private/image.png" not in str(error.value)


def test_provider_selection_prefers_explicit_gemini_and_auto_selects_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.delenv("IMAGE_ANALYSIS_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    analysis, embedding = providers.build_providers()

    assert isinstance(analysis, providers.GeminiImageAnalysisProvider)
    assert isinstance(embedding, providers.GeminiEmbeddingProvider)
