import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

import pytest
from fastapi import HTTPException

os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).parent))

from app import main


def actor(company_id="company-a", permissions=None):
    return SimpleNamespace(company_id=company_id, permissions=permissions or ["folder:read", "folder:use"])


def test_company_can_read_and_use_platform_folder_but_cannot_mutate():
    folder = {"folder_id": "platform-brand", "scope": "platform", "company_id": None, "name": "Brand"}

    main.authorize_folder_access(folder, actor(), "read")
    main.authorize_folder_access(folder, actor(), "use")
    with pytest.raises(HTTPException) as exc:
        main.authorize_folder_access(folder, actor(), "edit")
    assert exc.value.status_code == 403


def test_company_folder_requires_matching_company_and_permission():
    folder = {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}
    main.authorize_folder_access(folder, actor(permissions=["folder:edit"]), "edit")

    with pytest.raises(HTTPException) as exc:
        main.authorize_folder_access(folder, actor("company-b", ["folder:read"]), "read")
    assert exc.value.status_code == 403


def test_legacy_unfiled_content_remains_general_when_no_folder_id_exists():
    assert main.authorize_folder_access({"folder_id": None, "scope": None, "company_id": None, "name": "General"}, actor(), "use") is None


def test_folder_delete_removes_referenced_content(monkeypatch, tmp_path):
    folder = {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}
    knowledge_path = tmp_path / "knowledge.txt"
    reference_path = tmp_path / "reference.txt"
    knowledge_path.write_text("knowledge")
    reference_path.write_text("reference")
    knowledge = main.KnowledgeItemRecord(
        item_id="item-1", company_id="company-a", title="Guide", source="manual", description="",
        metadata={"stored_path": str(knowledge_path)}, folder_id=folder["folder_id"], created_at=datetime.utcnow(),
    )
    reference = main.CampaignReferenceRecord(
        reference_id="ref-1", campaign_id="campaign-1", file_name="reference.txt", file_type="text/plain",
        file_size=9, uploaded_at=datetime.utcnow().isoformat(), download_url="", folder="Brand", folder_id=folder["folder_id"],
    )

    class Persistence:
        def get_folder(self, folder_id):
            return folder if folder_id == folder["folder_id"] else None

        def delete_folder_with_content(self, folder_id):
            assert folder_id == folder["folder_id"]
            return [str(knowledge_path), str(reference_path)]

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor(permissions=["folder:delete"]))

    main.campaign_references["campaign-1"] = [reference]
    main.campaign_reference_files["campaign-1"] = {"ref-1": str(reference_path)}
    main.knowledge_items["company-a"] = [knowledge]

    result = main.delete_folder(object(), "company-brand")

    assert result == {"folder_id": "company-brand", "deleted": True}
    assert not knowledge_path.exists()
    assert not reference_path.exists()
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    main.knowledge_items.clear()


def test_in_memory_folder_delete_removes_referenced_content(monkeypatch, tmp_path):
    folder = {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand"}
    knowledge_path = tmp_path / "knowledge.txt"
    reference_path = tmp_path / "reference.txt"
    knowledge_path.write_text("knowledge")
    reference_path.write_text("reference")
    main.folders_cache.clear()
    main.folders_cache[folder["folder_id"]] = folder
    main.knowledge_items["company-a"] = [SimpleNamespace(folder_id=folder["folder_id"], metadata={"stored_path": str(knowledge_path)})]
    main.campaign_references["campaign-1"] = [SimpleNamespace(folder_id=folder["folder_id"], reference_id="ref-1")]
    main.campaign_reference_files["campaign-1"] = {"ref-1": str(reference_path)}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor(permissions=["folder:delete"]))

    result = main.delete_folder(object(), folder["folder_id"])
    assert result == {"folder_id": folder["folder_id"], "deleted": True}
    assert not knowledge_path.exists()
    assert not reference_path.exists()
    assert main.knowledge_items["company-a"] == []
    assert main.campaign_references["campaign-1"] == []
    main.knowledge_items.clear()
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    main.folders_cache.clear()


def test_platform_folder_delete_remains_forbidden_for_platform_admin(monkeypatch):
    folder = {"folder_id": "platform-brand", "scope": "platform", "company_id": None, "name": "Brand"}

    class Persistence:
        def get_folder(self, folder_id):
            return folder if folder_id == folder["folder_id"] else None

    monkeypatch.setattr(main, "persistence", Persistence())
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: True)

    with pytest.raises(HTTPException) as exc:
        main.delete_folder(object(), folder["folder_id"])
    assert exc.value.status_code == 403


def test_in_memory_internal_folder_listing_matches_persistent_platform_scope(monkeypatch):
    main.folders_cache.clear()


def test_in_memory_knowledge_listing_infers_unique_legacy_folder_but_not_ambiguous_or_unfiled(monkeypatch):
    def knowledge(item_id, category):
        return main.KnowledgeItemRecord(item_id=item_id, company_id="company-a", title=item_id, source="manual", description="", metadata={"category": category}, folder_id=None, created_at=datetime.utcnow())

    main.knowledge_items["company-a"] = [knowledge("unique", "Brand"), knowledge("ambiguous", "Shared"), knowledge("unfiled", "General")]
    main.folders_cache.update({
        "company-brand": {"folder_id": "company-brand", "scope": "company", "company_id": "company-a", "name": "Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
        "platform-shared": {"folder_id": "platform-shared", "scope": "platform", "company_id": None, "name": "Shared", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
        "company-shared": {"folder_id": "company-shared", "scope": "company", "company_id": "company-a", "name": "Shared", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
    })
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: type("Actor", (), {"company_id": "company-a"})())

    result = main.list_knowledge_items(object())
    by_id = {item.item_id: item.folder_id for item in result.items}
    assert by_id == {"unique": "company-brand", "ambiguous": None, "unfiled": None}
    main.knowledge_items.clear()
    main.folders_cache.clear()


def test_in_memory_knowledge_update_persists_selected_folder_id(monkeypatch):
    folder = {"folder_id": "target", "scope": "company", "company_id": "company-a", "name": "Target"}
    item = main.KnowledgeItemRecord(
        item_id="item-1", company_id="company-a", title="Guide", source="manual", description="",
        metadata={"category": "Old"}, folder_id=None, created_at=datetime.utcnow(),
    )
    main.knowledge_items["company-a"] = [item]
    main.folders_cache["target"] = {**folder, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor(permissions=["folder:edit"]))

    request = SimpleNamespace(headers={}, query_params={})
    updated = main.update_knowledge_item(request, "item-1", main.KnowledgeItemUpdateRequest(category="Target", folder_id="target"))
    assert updated.folder_id == "target"
    assert main.knowledge_items["company-a"][0].folder_id == "target"
    main.knowledge_items.clear()
    main.folders_cache.clear()


def test_in_memory_reference_move_persists_selected_folder_id(monkeypatch):
    campaign = SimpleNamespace(campaign_id="campaign-1", company_id="company-a")
    reference = main.CampaignReferenceRecord(
        reference_id="ref-1", campaign_id="campaign-1", file_name="guide.txt", file_type="text/plain",
        file_size=1, uploaded_at=datetime.utcnow().isoformat(), download_url="", folder="Old", folder_id=None,
    )
    main.campaign_references["campaign-1"] = [reference]
    main.campaign_reference_files["campaign-1"] = {"ref-1": __file__}
    main.folders_cache["target"] = {"folder_id": "target", "scope": "company", "company_id": "company-a", "name": "Target", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "store", SimpleNamespace(get_campaign=lambda _id: campaign))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor(permissions=["folder:edit"]))
    monkeypatch.setattr(main, "append_trace_event", lambda **_kwargs: None)

    request = SimpleNamespace(base_url="http://test", headers={}, query_params={})
    updated = main.update_campaign_reference("campaign-1", "ref-1", main.CampaignReferenceUpdateRequest(folder_id="target"), request)
    assert updated.folder_id == "target"
    assert main.campaign_references["campaign-1"][0].folder_id == "target"
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    main.folders_cache.clear()


def test_in_memory_reference_listing_infers_unambiguous_legacy_folder_id(monkeypatch):
    campaign = SimpleNamespace(campaign_id="campaign-1", company_id="company-a")
    reference = main.CampaignReferenceRecord(
        reference_id="ref-legacy", campaign_id="campaign-1", file_name="guide.txt", file_type="text/plain",
        file_size=1, uploaded_at=datetime.utcnow().isoformat(), download_url="", folder="brand", folder_id=None,
    )
    main.campaign_references["campaign-1"] = [reference]
    main.campaign_reference_files["campaign-1"] = {"ref-legacy": __file__}
    main.folders_cache["folder-brand"] = {"folder_id": "folder-brand", "scope": "company", "company_id": "company-a", "name": "Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "store", SimpleNamespace(get_campaign=lambda _id: campaign))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor())

    result = main.list_campaign_references("campaign-1", SimpleNamespace(base_url="http://test", headers={}))
    assert result.items[0].folder_id == "folder-brand"
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    main.folders_cache.clear()


def test_in_memory_reference_patch_without_folder_id_preserves_existing_association(monkeypatch):
    campaign = SimpleNamespace(campaign_id="campaign-1", company_id="company-a")
    reference = main.CampaignReferenceRecord(
        reference_id="ref-keep", campaign_id="campaign-1", file_name="guide.txt", file_type="text/plain",
        file_size=1, uploaded_at=datetime.utcnow().isoformat(), download_url="", folder="Old", folder_id="folder-old",
    )
    main.campaign_references["campaign-1"] = [reference]
    main.campaign_reference_files["campaign-1"] = {"ref-keep": __file__}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "store", SimpleNamespace(get_campaign=lambda _id: campaign))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor())
    monkeypatch.setattr(main, "append_trace_event", lambda **_kwargs: None)

    request = SimpleNamespace(base_url="http://test", headers={}, query_params={})
    updated = main.update_campaign_reference("campaign-1", "ref-keep", main.CampaignReferenceUpdateRequest(folder="Renamed"), request)
    assert updated.folder_id == "folder-old"
    main.campaign_references.clear()
    main.campaign_reference_files.clear()


def test_in_memory_reference_patch_with_explicit_null_clears_association(monkeypatch):
    campaign = SimpleNamespace(campaign_id="campaign-1", company_id="company-a")
    reference = main.CampaignReferenceRecord(
        reference_id="ref-clear", campaign_id="campaign-1", file_name="guide.txt", file_type="text/plain",
        file_size=1, uploaded_at=datetime.utcnow().isoformat(), download_url="", folder="Old", folder_id="folder-old",
    )
    main.campaign_references["campaign-1"] = [reference]
    main.campaign_reference_files["campaign-1"] = {"ref-clear": __file__}
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "store", SimpleNamespace(get_campaign=lambda _id: campaign))
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(main, "require_jwt", lambda _req: actor())
    monkeypatch.setattr(main, "append_trace_event", lambda **_kwargs: None)

    request = SimpleNamespace(base_url="http://test", headers={}, query_params={})
    updated = main.update_campaign_reference("campaign-1", "ref-clear", main.CampaignReferenceUpdateRequest(folder="General", folder_id=None), request)
    assert updated.folder_id is None
    main.campaign_references.clear()
    main.campaign_reference_files.clear()
    main.folders_cache.update({
        "platform": {"folder_id": "platform", "scope": "platform", "company_id": None, "name": "Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
        "company": {"folder_id": "company", "scope": "company", "company_id": "company-a", "name": "Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
    })
    monkeypatch.setattr(main, "persistence", None)
    monkeypatch.setattr(main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(main, "is_internal_api_key_request", lambda _req: True)

    result = main.list_folders(object())
    assert [item.folder_id for item in result.items] == ["platform"]
    main.folders_cache.clear()
