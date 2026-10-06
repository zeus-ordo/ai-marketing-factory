import io
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main


def request():
    return SimpleNamespace(headers=Headers())


def upload(name="new.png", content=b"png", content_type="image/png"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


class Persistence:
    def __init__(self, analysis=None):
        self.items = []
        self.analysis = analysis
        self.created_analysis = []
        self.reset_count = 0

    def create_knowledge_item(self, item):
        self.items.append(item)
        return item

    def create_image_analysis(self, item_id, analysis_version):
        self.created_analysis.append((item_id, analysis_version))
        self.analysis = self.analysis or {
            "item_id": item_id,
            "analysis_version": analysis_version,
            "analysis_status": "pending",
            "attributes": {},
            "retryable": True,
            "analyzed_at": None,
        }
        return self.analysis

    def get_image_analysis(self, item_id):
        return self.analysis if self.analysis and self.analysis["item_id"] == item_id else None

    def reset_image_analysis_for_retry(self, item_id, analysis_version):
        self.reset_count += 1
        if not self.analysis or self.analysis["analysis_status"] != "failed":
            return None
        self.analysis = {**self.analysis, "analysis_status": "pending", "analysis_version": analysis_version, "retryable": True}
        return self.analysis

    def list_knowledge_items(self, company_id):
        return [item for item in self.items if item["company_id"] == company_id]


@pytest.fixture
def configured(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: SimpleNamespace(company_id="company-a", sub="user-1", permissions=[]))
    monkeypatch.setattr(main, "resolve_folder_for_actor", lambda *_args: None)
    return persistence


def test_upload_returns_pending_and_enqueues(configured, monkeypatch):
    published = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda item_id, version: published.append((item_id, version)))

    result = main.upload_knowledge_item(request(), "New", "", "", None, "", upload())

    assert result.analysis is not None
    assert result.analysis.analysis_status == "pending"
    assert published == [(result.item_id, "image-rag-v1")]


def test_enqueue_failure_does_not_fail_upload(configured, monkeypatch):
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda *_args: (_ for _ in ()).throw(RuntimeError("redis unavailable")))

    result = main.upload_knowledge_item(request(), "New", "", "", None, "", upload())

    assert result.analysis.analysis_status == "pending"
    assert configured.items


def test_retry_requires_failed_record_and_is_idempotent(configured, monkeypatch):
    configured.analysis = {
        "item_id": "kh-1", "analysis_version": "image-rag-v1", "analysis_status": "failed",
        "attributes": {}, "retryable": True, "analyzed_at": None,
    }
    configured.items.append({"item_id": "kh-1", "company_id": "company-a", "created_at": datetime.utcnow()})
    published = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda item_id, version: published.append((item_id, version)))

    first = main.retry_knowledge_item_analysis(request(), "kh-1")
    second = main.retry_knowledge_item_analysis(request(), "kh-1")

    assert first.analysis_status == "pending"
    assert second.analysis_status == "pending"
    assert configured.reset_count == 1
    assert published == [("kh-1", "image-rag-v1")]


def test_analysis_status_is_safe_and_authorized(configured):
    configured.analysis = {
        "item_id": "kh-1", "analysis_version": "image-rag-v1", "analysis_status": "ready",
        "attributes": {"style": ["warm"]}, "retryable": False, "analyzed_at": None,
        "stored_path": "/private/image.png", "embedding": [0.1],
    }
    configured.items.append({"item_id": "kh-1", "company_id": "company-a", "created_at": datetime.utcnow()})

    response = main.get_knowledge_item_analysis(request(), "kh-1")

    assert response.analysis_status == "ready"
    assert not hasattr(response, "stored_path")
    assert not hasattr(response, "embedding")


def test_reference_pack_upload_enqueues(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())
    published = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda item_id, version: published.append((item_id, version)))

    result = main.upload_reference_pack_item(request(), "pack-1", "Reference", upload())

    assert published == [(result.item_id, "image-rag-v1")]


def test_upload_response_recursively_removes_private_paths():
    public = main._public_knowledge_item({
        "item_id": "kh-1",
        "metadata": {
            "stored_path": "/private/root.png",
            "nested": {"stored_path": "/private/nested.png", "label": "safe"},
        },
    })

    assert public["metadata"] == {"nested": {"label": "safe"}}


def test_in_memory_reference_pack_upload_caches_pending_analysis(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda *_args: None)
    main.knowledge_items.clear()

    result = main.upload_reference_pack_item(request(), "pack-1", "Reference", upload())

    cached = main.knowledge_items["platform"][0]
    assert result.analysis.analysis_status == "pending"
    assert cached.analysis.analysis_status == "pending"
