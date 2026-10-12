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
from app.persistence import PostgresPersistence  # noqa: E402


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


@pytest.mark.skipif(not os.getenv("CAMPAIGN_TEST_DATABASE_URL"), reason="requires disposable PostgreSQL fixture")
def test_folder_association_is_readable_after_persistence_reload():
    database_url = os.environ["CAMPAIGN_TEST_DATABASE_URL"]
    folder_id = f"task4-folder-{uuid4().hex}"
    reference_id = f"task4-reference-{uuid4().hex}"
    campaign_id = f"task4-campaign-{uuid4().hex}"
    first = PostgresPersistence(database_url)
    first.initialize()
    first.create_folder({
        "folder_id": folder_id,
        "scope": "company",
        "company_id": COMPANY_A,
        "name": "Task 4 Reload",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    first.save_campaign_reference(
        reference_id, campaign_id, "guide.txt", "text/plain", 1, datetime.utcnow(), __file__, "test",
        "Task 4 Reload", folder_id,
    )
    del first

    second = PostgresPersistence(database_url)
    reloaded = second.list_campaign_references(campaign_id)
    assert reloaded[0]["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_company_admin_role_assignment_is_same_company_and_non_platform(monkeypatch: pytest.MonkeyPatch):
    company_routes = membership_company_module()
    company_id = UUID("00000000-0000-0000-0000-000000000001")
    member_id = UUID("00000000-0000-0000-0000-000000000002")
    role_id = UUID("00000000-0000-0000-0000-000000000003")
    platform_role_id = UUID("00000000-0000-0000-0000-000000000004")
    cross_company_role_id = UUID("00000000-0000-0000-0000-000000000005")
    other_company_id = UUID("00000000-0000-0000-0000-000000000006")

    class Members:
        async def get_by_id(self, _member_id):
            return SimpleNamespace(member_id=member_id, company_id=company_id)

    class Roles:
        def __init__(self):
            self.updated = None

        async def get_by_id(self, selected):
            role_company = company_id if selected == role_id else other_company_id if selected == cross_company_role_id else None
            return SimpleNamespace(role_id=selected, company_id=role_company, is_system=selected == platform_role_id)

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

    with pytest.raises(HTTPException) as error:
        await company_routes.update_member_roles(company_id, member_id, company_routes.MemberRoleUpdateRequest(role_ids=[cross_company_role_id]), payload)
    assert error.value.status_code == 403
