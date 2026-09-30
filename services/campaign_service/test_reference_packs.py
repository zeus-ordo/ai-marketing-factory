import io
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import jwt
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app import auth


def req():
    return SimpleNamespace(headers=Headers(), base_url="http://test")


def upload(name="reference.png", content=b"png", content_type="image/png"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


class TimeoutStream:
    def __init__(self, content=b"png"):
        self.content = content
        self.reads = 0

    def read(self, _size=-1):
        self.reads += 1
        if self.reads == 1:
            return self.content
        return b""


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

    def list_knowledge_items(self, company_id):
        return [item for item in self.items if item.get("company_id") == company_id]

    def delete_reference_pack_item(self, pack_id, item_id):
        for item in self.items:
            if item.get("item_id") == item_id and item.get("reference_pack_id") == pack_id:
                item["deleted"] = True
                return True
        return False


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


def test_reference_pack_route_accepts_authenticated_platform_admin_jwt(monkeypatch):
    monkeypatch.setattr(auth, "JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(auth, "PLATFORM_ADMIN_KEY", "")
    token = jwt.encode({
        "sub": "platform-admin",
        "company_id": None,
        "email": "platform@example.test",
        "permissions": ["platform:admin"],
        "iat": 1,
        "exp": 4_000_000_000,
    }, "test-jwt-secret", algorithm="HS256")
    response = main.list_reference_packs(SimpleNamespace(headers=Headers({"authorization": f"Bearer {token}"})))
    assert response.total == 0


def test_reference_pack_route_rejects_generic_admin_or_wildcard_jwt(monkeypatch):
    monkeypatch.setattr(auth, "JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(auth, "PLATFORM_ADMIN_KEY", "")
    for permission in ("admin", "*"):
        token = jwt.encode({
            "sub": "non-platform-admin",
            "company_id": "company-1",
            "email": "admin@example.test",
            "permissions": [permission],
            "iat": 1,
            "exp": 4_000_000_000,
        }, "test-jwt-secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            main.list_reference_packs(SimpleNamespace(headers=Headers({"authorization": f"Bearer {token}"})))
        assert exc.value.status_code == 403


@pytest.mark.parametrize("operation", ["create", "update", "delete", "list_items", "upload", "delete_item"])
def test_every_reference_pack_mutation_or_item_route_requires_platform_admin(monkeypatch, operation):
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    pack = "pack-auth"
    calls = {
        "create": lambda: main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style")),
        "update": lambda: main.update_reference_pack(req(), pack, main.ReferencePackUpdateRequest(priority=1)),
        "delete": lambda: main.delete_reference_pack(req(), pack),
        "list_items": lambda: main.list_reference_pack_items(req(), pack),
        "upload": lambda: main.upload_reference_pack_item(req(), pack, title="Image", file=upload()),
        "delete_item": lambda: main.delete_reference_pack_item(req(), pack, "item-1"),
    }
    with pytest.raises(HTTPException) as exc:
        calls[operation]()
    assert exc.value.status_code == 403


def test_reference_pack_list_rejects_invalid_limit(monkeypatch):
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    with pytest.raises(HTTPException) as exc:
        main.list_reference_packs(req(), limit=0)
    assert exc.value.status_code == 400


def test_reference_pack_patch_rejects_blank_name(configured):
    pack = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style"))
    with pytest.raises(HTTPException) as exc:
        main.update_reference_pack(req(), pack.pack_id, main.ReferencePackUpdateRequest(name="  "))
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


def test_generic_knowledge_list_does_not_expose_pack_stored_path(configured):
    configured.items = [{
        "item_id": "item-1", "company_id": "platform", "title": "Image", "source": "manual",
        "description": "", "content_url": "/download", "metadata": {"stored_path": "C:/private/image.png", "file_name": "image.png"},
        "created_at": datetime.utcnow(), "folder_id": None, "reference_pack_id": "pack-1",
    }]
    result = main.list_knowledge_items(req())
    assert "stored_path" not in result.items[0].metadata
    assert result.items[0].metadata["file_name"] == "image.png"


def test_pack_upload_rejects_mismatched_image_mime(configured):
    pack = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style"))
    with pytest.raises(HTTPException) as exc:
        main.upload_reference_pack_item(req(), pack.pack_id, title="Image", file=upload(name="image.png", content_type="image/jpeg"))
    assert exc.value.status_code == 400
    assert exc.value.detail == "UNSUPPORTED_FILE_TYPE"


def test_pack_upload_validation_failure_removes_empty_platform_directory(configured, tmp_path):
    pack = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style"))
    with pytest.raises(HTTPException) as exc:
        main.upload_reference_pack_item(req(), pack.pack_id, title="Image", file=upload(name="image.gif", content_type="image/png"))
    assert exc.value.detail == "UNSUPPORTED_FILE_TYPE"
    assert not (tmp_path / "platform").exists()


def test_pack_upload_rejects_oversize_and_cleans_file(configured, monkeypatch, tmp_path):
    pack = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style"))
    monkeypatch.setattr(main, "REFERENCE_MAX_SIZE_BYTES", 2)
    with pytest.raises(HTTPException) as exc:
        main.upload_reference_pack_item(req(), pack.pack_id, title="Image", file=upload(content=b"123"))
    assert exc.value.detail == "FILE_TOO_LARGE"
    assert list(tmp_path.rglob("*")) == []


def test_pack_upload_timeout_cleans_file(configured, monkeypatch, tmp_path):
    pack = main.create_reference_pack(req(), main.ReferencePackCreateRequest(name="Pack", role="style"))
    monkeypatch.setattr(main, "REFERENCE_UPLOAD_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(main.time, "monotonic", lambda: 100.0)
    stream = UploadFile(filename="reference.png", file=TimeoutStream(), headers=Headers({"content-type": "image/png"}))
    clocks = iter((100.0, 100.0, 101.0))
    monkeypatch.setattr(main.time, "monotonic", lambda: next(clocks))
    with pytest.raises(HTTPException) as exc:
        main.upload_reference_pack_item(req(), pack.pack_id, title="Image", file=stream)
    assert exc.value.status_code == 504
    assert exc.value.detail == "UPLOAD_TIMEOUT"
    assert list(tmp_path.rglob("*")) == []


def test_pack_item_delete_rejects_item_from_another_pack(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    main.reference_packs.clear()
    main.knowledge_items.clear()
    now = datetime.utcnow()
    for pack_id in ("pack-a", "pack-b"):
        main.reference_packs[pack_id] = main.ReferencePackRecord(pack_id=pack_id, name=pack_id, role="style", created_at=now, updated_at=now)
    main.knowledge_items["platform"] = [main.KnowledgeItemRecord(item_id="item-a", company_id="platform", title="A", source="manual", created_at=now, reference_pack_id="pack-a")]
    with pytest.raises(HTTPException) as exc:
        main.delete_reference_pack_item(req(), "pack-b", "item-a")
    assert exc.value.status_code == 404
    assert main.knowledge_items["platform"][0].item_id == "item-a"


def test_pack_item_delete_removes_matching_in_memory_knowledge_item(monkeypatch):
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    main.reference_packs.clear()
    main.knowledge_items.clear()
    now = datetime.utcnow()
    main.reference_packs["pack-a"] = main.ReferencePackRecord(pack_id="pack-a", name="pack-a", role="style", created_at=now, updated_at=now)
    main.knowledge_items["platform"] = [main.KnowledgeItemRecord(item_id="item-a", company_id="platform", title="A", source="manual", created_at=now, reference_pack_id="pack-a")]
    result = main.delete_reference_pack_item(req(), "pack-a", "item-a")
    assert result.deleted is True
    assert main.knowledge_items["platform"] == []


def test_in_memory_pack_delete_removes_linked_items_from_platform_listing(monkeypatch):
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)
    main.reference_packs.clear()
    main.knowledge_items.clear()
    now = datetime.utcnow()
    main.reference_packs["pack-a"] = main.ReferencePackRecord(pack_id="pack-a", name="pack-a", role="style", created_at=now, updated_at=now)
    main.knowledge_items["platform"] = [
        main.KnowledgeItemRecord(item_id="item-a", company_id="platform", title="A", source="manual", created_at=now, reference_pack_id="pack-a"),
        main.KnowledgeItemRecord(item_id="item-b", company_id="platform", title="B", source="manual", created_at=now, reference_pack_id="pack-a"),
    ]
    result = main.delete_reference_pack(req(), "pack-a")
    listed = main.list_knowledge_items(req())
    assert result.deleted is True
    assert listed.total == 0
    assert listed.items == []
