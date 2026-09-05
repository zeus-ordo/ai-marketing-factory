from fastapi import HTTPException


ALLOWED_PERMISSIONS = frozenset(
    {
        "campaign:create",
        "campaign:edit",
        "campaign:delete",
        "campaign:read",
        "asset:create",
        "asset:edit",
        "asset:delete",
        "asset:read",
        "review:manage",
        "review:approve",
        "review:reject",
        "review:revision",
        "publish:execute",
        "member:assign_role",
        "member:manage",
        "role:manage",
        "folder:read",
        "folder:create",
        "folder:edit",
        "folder:delete",
        "folder:use",
    }
)

# Kept as a named alias for route and migration callers during the contract transition.
ALLOWED_ROLE_PERMISSIONS = ALLOWED_PERMISSIONS


def has_permission(permissions: list[str] | None, permission: str) -> bool:
    granted = set(permissions or [])
    return bool(granted & {"*", "admin", "platform:admin", permission})


def require_permission(payload: dict, permission: str) -> None:
    if not has_permission(payload.get("permissions"), permission):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def validate_permissions(permissions: list[str]) -> list[str]:
    deduped = list(dict.fromkeys(permissions))
    if any(permission not in ALLOWED_PERMISSIONS for permission in deduped):
        raise HTTPException(status_code=422, detail="Invalid permissions")
    return deduped


def add_manager_review_permission(permissions: list[str]) -> list[str]:
    if "review:manage" in permissions:
        return list(permissions)
    return [*permissions, "review:manage"]
