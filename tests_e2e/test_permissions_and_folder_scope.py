"""Deterministic offline acceptance coverage for permissions and folder scope."""

from __future__ import annotations

import os
import sys
from datetime import datetime
import importlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).parents[1]
CAMPAIGN_SERVICE = ROOT / "services" / "campaign_service"
MEMBERSHIP_SERVICE = ROOT / "services" / "membership_service"
os.environ.setdefault("CAMPAIGN_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "test-key")
sys.path.insert(0, str(CAMPAIGN_SERVICE))

from app import main as campaign_main  # noqa: E402


COMPANY_A = "company-a"
COMPANY_B = "company-b"


def membership_company_module():
    """Load membership routes without replacing the campaign app namespace."""
    campaign_modules = {name: module for name, module in sys.modules.items() if name == "app" or name.startswith("app.")}
    for name in campaign_modules:
        del sys.modules[name]
    sys.path.insert(0, str(MEMBERSHIP_SERVICE))
    try:
        module = importlib.import_module("app.routes.company")
    finally:
        sys.path.pop(0)
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
        sys.modules.update(campaign_modules)
    return module


def actor(company_id: str, permissions: list[str]) -> SimpleNamespace:
    return SimpleNamespace(company_id=company_id, permissions=permissions)


def request() -> SimpleNamespace:
    return SimpleNamespace(headers={}, query_params={})


def test_manager_review_access_and_folder_scope_are_enforced(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(campaign_main, "persistence", None)
    monkeypatch.setattr(campaign_main, "folders_cache", {})
    monkeypatch.setattr(campaign_main, "is_internal_api_key_request", lambda _req: False)
    campaign_main.folders_cache["platform-brand"] = {
        "folder_id": "platform-brand", "scope": "platform", "company_id": None,
        "name": "Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    }
    campaign_main.folders_cache["company-a-brand"] = {
        "folder_id": "company-a-brand", "scope": "company", "company_id": COMPANY_A,
        "name": "Company Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    }
    campaign_main.folders_cache["company-b-brand"] = {
        "folder_id": "company-b-brand", "scope": "company", "company_id": COMPANY_B,
        "name": "Other Brand", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    }

    monkeypatch.setattr(campaign_main, "require_jwt", lambda _req: actor(COMPANY_A, ["folder:read", "folder:use"]))
    visible = campaign_main.list_folders(request())
    assert {item.folder_id for item in visible.items} == {"platform-brand", "company-a-brand"}
    campaign_main.authorize_folder_access(campaign_main.folders_cache["platform-brand"], actor(COMPANY_A, ["folder:use"]), "use")
    with pytest.raises(HTTPException, match="read-only"):
        campaign_main.authorize_folder_access(campaign_main.folders_cache["platform-brand"], actor(COMPANY_A, ["folder:edit"]), "edit")
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: True)
    updated = campaign_main.update_folder(request(), "platform-brand", campaign_main.FolderUpdateRequest(name="Platform Brand"))
    assert updated.name == "Platform Brand"

    monkeypatch.setattr(campaign_main, "require_jwt", lambda _req: actor(COMPANY_A, ["review:manage"]))
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: False)
    campaign_main.require_review_action_access(request())
    with pytest.raises(HTTPException):
        campaign_main.require_any_permission(actor(COMPANY_A, ["folder:read"]), {"review:manage"})


def test_folder_association_is_readable_after_persistence_reload(monkeypatch: pytest.MonkeyPatch):
    class Persistence:
        records: dict[str, dict] = {}

        def list_campaign_references(self, campaign_id):
            return [item for item in self.records.values() if item["campaign_id"] == campaign_id]

        def get_folder(self, folder_id):
            return {"folder_id": folder_id, "scope": "company", "company_id": COMPANY_A, "name": "Brand"}

        def list_folders(self, _company_id):
            return [self.get_folder("company-a-brand")]

    first = Persistence()
    Persistence.records["ref-1"] = {
        "reference_id": "ref-1", "campaign_id": "campaign-1", "file_name": "guide.txt",
        "file_type": "text/plain", "file_size": 4, "uploaded_at": "2026-09-06T00:00:00Z",
        "stored_path": __file__, "folder": "Brand", "folder_id": "company-a-brand",
    }
    second = Persistence()
    monkeypatch.setattr(campaign_main, "persistence", second)
    monkeypatch.setattr(campaign_main, "store", SimpleNamespace(get_campaign=lambda _id: SimpleNamespace(company_id=COMPANY_A)))
    monkeypatch.setattr(campaign_main, "is_platform_admin_request", lambda _req: False)
    monkeypatch.setattr(campaign_main, "is_internal_api_key_request", lambda _req: False)
    monkeypatch.setattr(campaign_main, "require_jwt", lambda _req: actor(COMPANY_A, ["folder:read"]))
    req = request()
    req.base_url = "http://test"
    result = campaign_main.list_campaign_references("campaign-1", req)
    assert result.items[0].folder_id == "company-a-brand"


@pytest.mark.asyncio
async def test_company_admin_role_assignment_is_same_company_and_non_platform(monkeypatch: pytest.MonkeyPatch):
    company_routes = membership_company_module()
    company_id = UUID("00000000-0000-0000-0000-000000000001")
    member_id = UUID("00000000-0000-0000-0000-000000000002")
    role_id = UUID("00000000-0000-0000-0000-000000000003")
    platform_role_id = UUID("00000000-0000-0000-0000-000000000004")

    class Members:
        async def get_by_id(self, _member_id):
            return SimpleNamespace(member_id=member_id, company_id=company_id)

    class Roles:
        def __init__(self):
            self.updated = None

        async def get_by_id(self, selected):
            return SimpleNamespace(role_id=selected, company_id=company_id if selected == role_id else None, is_system=selected == platform_role_id)

        async def set_member_roles(self, *args, **kwargs):
            self.updated = (args, kwargs)

    roles = Roles()
    monkeypatch.setattr(company_routes, "member_repo", Members())
    monkeypatch.setattr(company_routes, "role_repo", roles)
    payload = {"sub": str(uuid4()), "company_id": str(company_id), "permissions": ["member:assign_role"]}
    result = await company_routes.update_member_roles(company_id, member_id, company_routes.MemberRoleUpdateRequest(role_ids=[role_id]), payload)
    assert result == {"message": "Roles updated"}
    assert roles.updated is not None

    with pytest.raises(HTTPException) as error:
        await company_routes.update_member_roles(company_id, member_id, company_routes.MemberRoleUpdateRequest(role_ids=[platform_role_id]), payload)
    assert error.value.status_code == 422
