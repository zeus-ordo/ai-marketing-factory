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


def req():
    return SimpleNamespace(headers=Headers(), base_url="http://test")


def upload(name="reference.png", content=b"png", content_type="image/png"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


class Persistence:
    def __init__(self):
        self.packs = {}
        self.items = []

    def create_reference_pack(self, pack):
        self.packs[pack["pack_id"]] = pack
        return pack

    def get_reference_pack(self, pack_id):
        return self.packs.get(pack_id)

    def list_reference_packs(self, role=None, industry=None, is_active=None, limit=100):
        return list(self.packs.values())[:limit]

    def update_reference_pack(self, pack_id, updates):
        self.packs[pack_id].update(updates)
        return self.packs[pack_id]

    def create_knowledge_item(self, item):
        self.items.append(item)
        return item


@pytest.fixture
def configured(monkeypatch, tmp_path):
    persistence = Persistence()
    monkeypatch.setattr(main, "persistence", persistence)
    monkeypatch.setattr(main, "KNOWLEDGE_UPLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    return persistence


def test_reference_pack_models_reject_invalid_role_and_limit():
    with pytest.raises(ValueError):
        main.ReferencePackCreateRequest(name="Pack", role="invalid")
    with pytest.raises(ValueError):
        main.ReferencePackCreateRequest(name="Pack", role="style", max_images=0)


def test_reference_pack_routes_return_403_for_non_admin(monkeypatch):
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    with pytest.raises(HTTPException) as exc:
        main.list_reference_packs(req())
    assert exc.value.status_code == 403


def test_reference_pack_list_rejects_invalid_limit(monkeypatch):
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    with pytest.raises(HTTPException) as exc:
        main.list_reference_packs(req(), limit=0)
    assert exc.value.status_code == 400


def test_reference_pack_create_list_and_update(configured):
    persistence = configured
    created = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Style", role="style"))
    assert created.scope == "platform"
    assert created.role == "style"
    assert "stored_path" not in created.model_dump()
    listed = main.list_reference_packs(req())
    assert listed.total == 1
    updated = main.update_reference_pack(req(), created.pack_id, main.ReferencePackUpdateRequest(priority=4))
    assert updated.priority == 4
    assert persistence.packs[created.pack_id]["priority"] == 4


def test_reference_pack_upload_links_image_knowledge_without_exposing_path(configured, monkeypatch):
    persistence = configured
    pack = main.ReferencePackRecord(
        pack_id="pack-1", name="Style", role="style", scope="platform", industry=None,
        selection_mode="optional", max_images=2, priority=1, is_active=True,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    persistence.packs[pack.pack_id] = pack.model_dump(mode="python")
    persistence.items = [{"item_id": "item-1", "reference_pack_id": pack.pack_id}]
    result = main.upload_reference_pack_item(req(), pack.pack_id, title="Example", file=upload())
    assert result.reference_pack_id == pack.pack_id
    assert result.file_type == "image/png"
    assert "stored_path" not in result.model_dump()
    assert persistence.items[-1]["reference_pack_id"] == pack.pack_id
