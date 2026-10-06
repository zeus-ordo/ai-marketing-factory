import pytest
from fastapi.testclient import TestClient

from app import main


class FakeStore:
    def __init__(self, image_path: str, status: str = "pending"):
        self.analysis = {
            "item_id": "item-1",
            "analysis_version": "image-rag-v1",
            "analysis_status": status,
        }
        self.item = {
            "item_id": "item-1",
            "title": "Food image",
            "description": "A bowl on a table",
            "stored_path": image_path,
            "mime_type": "image/png",
        }
        self.calls = []

    def get_image_analysis(self, item_id, analysis_version=None):
        if item_id != self.analysis["item_id"]:
            return None
        if analysis_version is not None and analysis_version != self.analysis["analysis_version"]:
            return None
        return self.analysis

    def get_image_item(self, item_id):
        return self.item if item_id == self.item["item_id"] else None

    def claim_image_analysis(self, item_id, analysis_version):
        self.calls.append("claim")
        if self.analysis["analysis_status"] != "pending":
            return False
        self.analysis["analysis_status"] = "processing"
        return True

    def complete_image_analysis(self, item_id, analysis_version, attributes, embedding, embedding_model):
        self.calls.append(("complete", attributes, embedding, embedding_model))
        self.analysis["analysis_status"] = "ready"
        return {"item_id": item_id, "analysis_status": "ready"}

    def fail_image_analysis(self, item_id, analysis_version, error_code, error_detail):
        self.calls.append(("fail", error_code, error_detail))
        self.analysis["analysis_status"] = "failed"
        return {"item_id": item_id, "analysis_status": "failed"}


class FakeAnalysisProvider:
    def __init__(self, calls):
        self.calls = calls

    def analyze(self, image_path, mime_type, title, description):
        self.calls.append(("analyze", image_path, mime_type))
        return {"objects": ["bowl"], "style": "warm"}


class FakeEmbeddingProvider:
    def __init__(self, calls):
        self.calls = calls

    def embed(self, text):
        self.calls.append(("embed", text))
        return [0.1, 0.2]


def test_job_transitions_pending_to_ready(monkeypatch, tmp_path):
    image = tmp_path / "new.png"
    image.write_bytes(b"png")
    calls = []
    store = FakeStore(str(image))
    monkeypatch.setattr(main, "persistence", store)
    monkeypatch.setattr(main.providers, "analysis_provider", FakeAnalysisProvider(calls))
    monkeypatch.setattr(main.providers, "embedding_provider", FakeEmbeddingProvider(calls))

    result = main.process_image_enrichment_job({"item_id": "item-1", "analysis_version": "image-rag-v1"})

    assert result == {"item_id": "item-1", "status": "ready"}
    assert store.calls[0] == "claim"
    assert calls[0][0] == "analyze"
    assert calls[1][0] == "embed"
    assert "stored_path" not in result
    assert "private" not in calls[1][1].lower()


def test_provider_failure_is_retryable_and_redacted(monkeypatch, tmp_path):
    image = tmp_path / "new.png"
    image.write_bytes(b"png")
    store = FakeStore(str(image))
    monkeypatch.setattr(main, "persistence", store)

    class FailingProvider:
        def analyze(self, *args):
            raise RuntimeError("secret api key and /private/image.png")

    monkeypatch.setattr(main.providers, "analysis_provider", FailingProvider())

    result = main.process_image_enrichment_job({"item_id": "item-1", "analysis_version": "image-rag-v1"})

    assert result["status"] == "failed"
    failure = store.calls[-1]
    assert failure[0] == "fail"
    assert failure[1] == "PROVIDER_ERROR"
    assert "/private/image.png" not in failure[2]
    assert "secret api key" not in failure[2]


def test_ready_job_is_idempotent_without_provider_calls(monkeypatch, tmp_path):
    store = FakeStore(str(tmp_path / "already.png"), status="ready")
    monkeypatch.setattr(main, "persistence", store)

    class UnexpectedProvider:
        def analyze(self, *args):
            raise AssertionError("provider should not be called")

    monkeypatch.setattr(main.providers, "analysis_provider", UnexpectedProvider())

    result = main.process_image_enrichment_job({"item_id": "item-1", "analysis_version": "image-rag-v1"})

    assert result == {"item_id": "item-1", "status": "already_complete"}
    assert store.calls == []


def test_job_queries_the_requested_analysis_version(monkeypatch, tmp_path):
    store = FakeStore(str(tmp_path / "versioned.png"))
    store.analysis_versions = {
        "image-rag-v1": {"item_id": "item-1", "analysis_version": "image-rag-v1", "analysis_status": "ready"},
        "image-rag-v2": {"item_id": "item-1", "analysis_version": "image-rag-v2", "analysis_status": "pending"},
    }
    requested = []

    def get_version(item_id, analysis_version=None):
        requested.append((item_id, analysis_version))
        return store.analysis_versions.get(analysis_version)

    monkeypatch.setattr(store, "get_image_analysis", get_version)
    monkeypatch.setattr(main, "persistence", store)
    monkeypatch.setattr(main.providers, "analysis_provider", FakeAnalysisProvider([]))
    monkeypatch.setattr(main.providers, "embedding_provider", FakeEmbeddingProvider([]))

    result = main.process_image_enrichment_job({"item_id": "item-1", "analysis_version": "image-rag-v2"})

    assert result["status"] == "ready"
    assert requested == [("item-1", "image-rag-v2")]


def test_internal_endpoint_rejects_requests_without_configured_key(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_API_KEY", "")
    client = TestClient(main.app)

    response = client.post("/internal/v1/image-enrichment", json={"item_id": "item-1", "analysis_version": "image-rag-v1"})

    assert response.status_code == 401


def test_arbitrary_provider_exception_code_is_not_persisted(monkeypatch, tmp_path):
    store = FakeStore(str(tmp_path / "unsafe-code.png"))
    monkeypatch.setattr(main, "persistence", store)

    class UnsafeProvider:
        def analyze(self, *args):
            error = RuntimeError("provider failure")
            error.code = "SECRET_INTERNAL_CODE"
            raise error

    monkeypatch.setattr(main.providers, "analysis_provider", UnsafeProvider())

    result = main.process_image_enrichment_job({"item_id": "item-1", "analysis_version": "image-rag-v1"})

    assert result["status"] == "failed"
    assert store.calls[-1][1] == "PROVIDER_ERROR"
