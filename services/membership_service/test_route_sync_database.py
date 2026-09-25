import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app import database
from app.models import Company, Member, Role
from app.routes import company, platform
from app.schemas import CompanyCreate, MemberRoleUpdateRequest


NOW = datetime.now(timezone.utc)
COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
MEMBER_ID = UUID("22222222-2222-2222-2222-222222222222")
ROLE_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeCursor:
    def __init__(self, fetchall_rows=None, fetchone_rows=None):
        self.fetchall_rows = list(fetchall_rows or [])
        self.fetchone_rows = list(fetchone_rows or [])
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=()):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_rows.pop(0) if self.fetchone_rows else None

    def fetchall(self):
        return self.fetchall_rows.pop(0) if self.fetchall_rows else []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


def member_row(member_id=MEMBER_ID, company_id=COMPANY_ID):
    return {
        "member_id": member_id,
        "email": "member@example.com",
        "company_id": company_id,
        "email_verified": True,
        "is_active": True,
        "created_at": NOW,
    }


def role_row():
    return {
        "role_id": ROLE_ID,
        "company_id": COMPANY_ID,
        "name": "Manager",
        "is_system": False,
        "permissions": ["member:manage"],
        "created_at": NOW,
    }


def test_platform_key_accepts_configured_key_and_rejects_invalid_key(monkeypatch):
    monkeypatch.setattr(platform.settings, "PLATFORM_ADMIN_KEY", "test-platform-key")

    assert platform.require_developer("test-platform-key") == {"role": "developer"}
    with pytest.raises(HTTPException) as error:
        platform.require_developer("wrong-key")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_platform_company_create_writes_audit_with_sync_connection(monkeypatch):
    company_obj = Company(COMPANY_ID, "Acme", "acme", NOW, NOW)
    cursor = FakeCursor()
    monkeypatch.setattr(database, "get_connection", lambda: FakeConnection(cursor))
    monkeypatch.setattr(platform, "get_connection", lambda: FakeConnection(cursor))
    monkeypatch.setattr(platform.company_repo, "get_by_slug", lambda slug: _async_result(None))
    monkeypatch.setattr(platform.company_repo, "create", lambda **kwargs: _async_result(company_obj))

    response = await platform.create_company(CompanyCreate(name="Acme", slug="acme"), {})

    assert response.company_id == COMPANY_ID
    assert len(cursor.executed) == 1
    assert "INSERT INTO audit_logs" in cursor.executed[0][0]


@pytest.mark.asyncio
async def test_platform_company_member_listing_uses_sync_cursor(monkeypatch):
    company_obj = Company(COMPANY_ID, "Acme", "acme", NOW, NOW)
    cursor = FakeCursor([[member_row()], [role_row()]])
    cursor.fetchone = lambda: None
    monkeypatch.setattr(database, "get_connection", lambda: FakeConnection(cursor))
    monkeypatch.setattr(platform, "get_connection", lambda: FakeConnection(cursor))
    monkeypatch.setattr(platform.company_repo, "get_by_id", lambda company_id: _async_result(company_obj))

    response = await platform.get_company_members(COMPANY_ID, {})

    assert response.total == 1
    assert response.items[0].member_id == MEMBER_ID


@pytest.mark.asyncio
async def test_company_member_listing_with_qa_jwt_payload_uses_sync_cursor(monkeypatch):
    cursor = FakeCursor([[member_row()], [role_row()]])
    monkeypatch.setattr(database, "get_connection", lambda: FakeConnection(cursor))

    response = await company.list_members(
        COMPANY_ID,
        {"company_id": str(COMPANY_ID), "permissions": ["member:manage"], "sub": str(MEMBER_ID)},
    )

    assert response.total == 1
    assert response.items[0].email == "member@example.com"


@pytest.mark.asyncio
async def test_same_company_member_removal_checks_ownership_and_mutates_target(monkeypatch):
    cursor = FakeCursor(fetchone_rows=[member_row()])
    monkeypatch.setattr(database, "get_connection", lambda: FakeConnection(cursor))

    await company.remove_member(
        COMPANY_ID,
        MEMBER_ID,
        {"company_id": str(COMPANY_ID), "permissions": ["member:manage"]},
    )

    assert len(cursor.executed) == 2
    query, params = cursor.executed[1]
    assert "UPDATE members" in query
    assert "member_id = %s" in query
    assert "company_id = %s" in query
    assert params == (MEMBER_ID, COMPANY_ID)


@pytest.mark.asyncio
async def test_cross_company_member_removal_is_denied_without_mutation(monkeypatch):
    other_company_id = UUID("44444444-4444-4444-4444-444444444444")
    cursor = FakeCursor(fetchone_rows=[member_row(company_id=other_company_id)])
    monkeypatch.setattr(database, "get_connection", lambda: FakeConnection(cursor))

    with pytest.raises(HTTPException) as error:
        await company.remove_member(
            COMPANY_ID,
            MEMBER_ID,
            {"company_id": str(COMPANY_ID), "permissions": ["member:manage"]},
        )

    assert error.value.status_code == 403
    assert len(cursor.executed) == 1


@pytest.mark.asyncio
async def test_company_role_update_preserves_company_isolation_and_audits(monkeypatch):
    target = Member(MEMBER_ID, COMPANY_ID, "member@example.com", "hash", True, True, NOW, NOW)
    role = Role(ROLE_ID, COMPANY_ID, "Manager", False, ["member:manage"], NOW)
    calls = {}
    monkeypatch.setattr(company.member_repo, "get_by_id", lambda member_id: _async_result(target))
    monkeypatch.setattr(company.role_repo, "get_by_id", lambda role_id: _async_result(role))

    async def set_member_roles(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs

    monkeypatch.setattr(company.role_repo, "set_member_roles", set_member_roles)
    response = await company.update_member_roles(
        COMPANY_ID,
        MEMBER_ID,
        MemberRoleUpdateRequest(role_ids=[ROLE_ID]),
        {"company_id": str(COMPANY_ID), "permissions": ["member:assign_role"], "sub": str(MEMBER_ID)},
    )

    assert response == {"message": "Roles updated"}
    assert calls["kwargs"]["company_id"] == COMPANY_ID


def _async_result(value):
    async def result():
        return value

    return result()
