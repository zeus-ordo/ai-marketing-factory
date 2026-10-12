import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main


class Persistence:
    def __init__(self):
        self.items = []

    def create_knowledge_item(self, item):
        self.items.append(item)
        return item


def test_txt_reference_pack_upload_persists_without_image_analysis(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())
    enqueued = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda *args: enqueued.append(args))

    content = "Use the approved brand tone.".encode("utf-8")
    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Brand guidelines"},
        files={"file": ("brand-guidelines.txt", content, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "brand-guidelines.txt"
    assert body["file_type"] == "text/plain"
    assert body["file_size"] == len(content)
    assert body["analysis"] is None
    assert "stored_path" not in body
    assert enqueued == []
    assert persistence.items[-1]["reference_pack_id"] == "pack-1"
    assert persistence.items[-1]["metadata"]["reference_pack_id"] == "pack-1"


def test_markdown_reference_pack_upload_persists_without_image_analysis(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())
    enqueued = []
    monkeypatch.setattr(main, "enqueue_image_enrichment", lambda *args: enqueued.append(args))

    content = "# Campaign notes\n".encode("utf-8")
    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-2/items/upload",
        data={"title": "Campaign notes"},
        files={"file": ("campaign-notes.md", content, "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "campaign-notes.md"
    assert body["file_type"] == "text/markdown"
    assert body["file_size"] == len(content)
    assert body["analysis"] is None
    assert "stored_path" not in body
    assert enqueued == []
    assert persistence.items[-1]["reference_pack_id"] == "pack-2"


def test_octet_stream_text_upload_normalizes_file_type_in_response_and_persistence(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())

    content = "# Campaign notes\n".encode("utf-8")
    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-3/items/upload",
        data={"title": "Campaign notes"},
        files={"file": ("campaign-notes.md", content, "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["file_type"] == "text/markdown"
    assert persistence.items[-1]["metadata"]["file_type"] == "text/markdown"


@pytest.mark.parametrize("name", ["brief.docx", "brief.pdf", "brief.exe"])
def test_reference_pack_upload_rejects_unsupported_text_formats(monkeypatch, tmp_path, name):
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())

    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Unsupported"},
        files={"file": (name, b"content", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize(
    ("name", "content_type"),
    [("brief.txt", "text/markdown"), ("brief.md", "text/plain")],
)
def test_reference_pack_upload_rejects_mismatched_text_mime(monkeypatch, tmp_path, name, content_type):
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())

    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Mismatched"},
        files={"file": (name, b"content", content_type)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "UNSUPPORTED_FILE_TYPE"


def test_reference_pack_upload_rejects_invalid_utf8_and_cleans_file(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    monkeypatch.setattr(main, "_get_pack_or_404", lambda _pack_id: object())

    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Invalid"},
        files={"file": ("invalid.txt", b"\xff\xfe", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_UTF8"
    assert persistence.items == []
    assert list(tmp_path.rglob("*")) == []


def test_reference_pack_text_upload_requires_platform_admin(monkeypatch):
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)

    response = TestClient(main.app).post(
        "/api/v1/reference-packs/pack-1/items/upload",
        data={"title": "Notes"},
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "PLATFORM_ADMIN_REQUIRED"


def test_reference_pack_text_classifier_accepts_octet_stream():
    assert main._reference_pack_upload_kind("notes.txt", "application/octet-stream") == "text"
    assert main._reference_pack_upload_kind("notes.md", "application/octet-stream") == "text"
