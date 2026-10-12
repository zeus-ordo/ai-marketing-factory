import json
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app.repositories import role as role_module
from app.repositories.role import RoleRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement, params=()):
        self.connection.statements.append((" ".join(statement.split()), params))
        if self.connection.fail_on_audit and "INSERT INTO audit_logs" in statement:
            raise RuntimeError("audit write failed")


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.transaction_started = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.connection.rollback_count += 1
        else:
            self.connection.commit_count += 1
        return False


class FakeConnection:
    def __init__(self, *, fail_on_audit=False):
        self.fail_on_audit = fail_on_audit
        self.statements = []
        self.transaction_started = False
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return FakeCursor(self)

    def transaction(self):
        return FakeTransaction(self)


@pytest.mark.asyncio
async def test_set_member_roles_commits_links_and_audit_with_only_expected_fields(monkeypatch):
    connection = FakeConnection()

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(role_module, "get_connection", fake_get_connection)
    actor_id, member_id, company_id, role_ids = uuid4(), uuid4(), uuid4(), [uuid4(), uuid4()]

    await RoleRepository().set_member_roles(member_id, role_ids, actor_id=actor_id, company_id=company_id)

    assert connection.transaction_started is True
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    audit = next(params for statement, params in connection.statements if "INSERT INTO audit_logs" in statement)
    assert audit[:5] == (actor_id, company_id, "member.roles.update", "member", str(member_id))
    metadata = json.loads(audit[5])
    assert metadata == {
        "actor_id": str(actor_id),
        "member_id": str(member_id),
        "role_ids": [str(role_id) for role_id in role_ids],
        "result": "success",
    }
    assert not any(secret in json.dumps(metadata).lower() for secret in ("password", "token", "secret"))


@pytest.mark.asyncio
async def test_set_member_roles_rolls_back_links_when_audit_fails(monkeypatch):
    connection = FakeConnection(fail_on_audit=True)

    @contextmanager
    def fake_get_connection():
        yield connection

    monkeypatch.setattr(role_module, "get_connection", fake_get_connection)

    with pytest.raises(RuntimeError, match="audit write failed"):
        await RoleRepository().set_member_roles(uuid4(), [uuid4()], actor_id=uuid4(), company_id=uuid4())

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
