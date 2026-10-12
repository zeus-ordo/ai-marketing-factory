import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]
sys.path.insert(0, str(Path(__file__).parent))

from app.permissions import ALLOWED_PERMISSIONS, add_manager_review_permission, has_permission, require_permission, validate_permissions


def test_allowed_permissions_include_canonical_contract_and_migration_names():
    assert {
        "review:manage",
        "member:assign_role",
        "folder:read",
        "folder:create",
        "folder:edit",
        "folder:delete",
        "folder:use",
        "review:approve",
        "review:reject",
        "review:revision",
        "member:manage",
    }.issubset(ALLOWED_PERMISSIONS)


@pytest.mark.parametrize("permissions", [["*"], ["admin"], ["platform:admin"]])
def test_shared_permission_checker_supports_bypass_permissions(permissions):
    assert has_permission(permissions, "review:manage")
    require_permission({"permissions": permissions}, "review:manage")


def test_shared_permission_checker_denies_unrelated_permission():
    with pytest.raises(HTTPException) as error:
        require_permission({"permissions": ["role:manage"]}, "review:manage")

    assert error.value.status_code == 403


def test_role_validation_accepts_canonical_permissions_and_rejects_unknown_values():
    permissions = validate_permissions(["review:manage", "member:assign_role", "folder:read", "folder:use"])
    assert permissions == ["review:manage", "member:assign_role", "folder:read", "folder:use"]

    with pytest.raises(HTTPException) as error:
        validate_permissions(["review:manage", "unknown:permission"])

    assert error.value.status_code == 422


def test_manager_default_permission_seed_is_additive_and_idempotent():
    existing = ["member:manage", "review:approve"]

    seeded = add_manager_review_permission(existing)
    reseeded = add_manager_review_permission(seeded)

    assert seeded == ["member:manage", "review:approve", "review:manage"]
    assert reseeded == seeded
    assert "member:assign_role" not in seeded
