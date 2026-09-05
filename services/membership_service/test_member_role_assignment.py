import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app.models import Member, Role
from app.routes import company
from app.schemas import MemberRoleUpdateRequest


COMPANY_ID = uuid4()
OTHER_COMPANY_ID = uuid4()
ACTOR_ID = uuid4()
TARGET_ID = uuid4()
ROLE_ID = uuid4()
PLATFORM_ROLE_ID = uuid4()


def member(member_id: UUID, company_id: UUID) -> Member:
    now = datetime.now()
    return Member(member_id, company_id, "member@example.com", "hash", True, True, now, now)


def role(role_id: UUID, company_id: UUID | None, *, is_system: bool = False) -> Role:
    return Role(role_id, company_id, "role", is_system, [], datetime.now())


class FakeMembers:
    def __init__(self, target_company_id=COMPANY_ID):
        self.target_company_id = target_company_id

    async def get_by_id(self, member_id: UUID):
        return {
            TARGET_ID: member(TARGET_ID, self.target_company_id),
            ACTOR_ID: member(ACTOR_ID, COMPANY_ID),
        }.get(member_id)


class FakeRoles:
    def __init__(self, roles):
        self.roles = roles
        self.updated = None

    async def get_by_id(self, role_id: UUID):
        return self.roles.get(role_id)

    async def set_member_roles(self, member_id, role_ids, *, actor_id, company_id):
        self.updated = (member_id, role_ids, actor_id, company_id)


async def call_update(
    monkeypatch,
    permissions,
    *,
    company_id=COMPANY_ID,
    member_id=TARGET_ID,
    target_company_id=COMPANY_ID,
    role_ids=None,
):
    roles = FakeRoles({ROLE_ID: role(ROLE_ID, COMPANY_ID), PLATFORM_ROLE_ID: role(PLATFORM_ROLE_ID, None, is_system=True)})
    monkeypatch.setattr(company, "member_repo", FakeMembers(target_company_id))
    monkeypatch.setattr(company, "role_repo", roles)
    try:
        result = await company.update_member_roles(
            company_id,
            member_id,
            MemberRoleUpdateRequest(role_ids=role_ids if role_ids is not None else [ROLE_ID]),
            {"sub": str(ACTOR_ID), "company_id": str(COMPANY_ID), "permissions": permissions},
        )
        return result, roles
    except HTTPException as error:
        return error, roles


@pytest.mark.asyncio
async def test_same_company_assignment_succeeds(monkeypatch):
    result, roles = await call_update(monkeypatch, ["member:assign_role"])
    assert result == {"message": "Roles updated"}
    assert roles.updated == (TARGET_ID, [ROLE_ID], ACTOR_ID, COMPANY_ID)


@pytest.mark.asyncio
async def test_cross_company_target_is_denied(monkeypatch):
    result, _ = await call_update(monkeypatch, ["member:assign_role"], target_company_id=OTHER_COMPANY_ID)
    assert result.status_code == 403


@pytest.mark.asyncio
async def test_platform_role_is_denied(monkeypatch):
    result, _ = await call_update(monkeypatch, ["member:assign_role"], role_ids=[PLATFORM_ROLE_ID])
    assert result.status_code == 422


@pytest.mark.asyncio
async def test_unknown_role_id_is_rejected(monkeypatch):
    result, _ = await call_update(monkeypatch, ["member:assign_role"], role_ids=[uuid4()])
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_manager_without_assign_role_is_denied(monkeypatch):
    result, _ = await call_update(monkeypatch, ["role:manage"])
    assert result.status_code == 403


@pytest.mark.asyncio
async def test_compatibility_manager_permission_is_allowed(monkeypatch):
    result, _ = await call_update(monkeypatch, ["member:manage"])
    assert result == {"message": "Roles updated"}


@pytest.mark.asyncio
async def test_self_edit_remains_allowed_and_is_audited(monkeypatch):
    result, roles = await call_update(monkeypatch, ["member:assign_role"], member_id=ACTOR_ID)
    assert result == {"message": "Roles updated"}
    assert roles.updated == (ACTOR_ID, [ROLE_ID], ACTOR_ID, COMPANY_ID)
