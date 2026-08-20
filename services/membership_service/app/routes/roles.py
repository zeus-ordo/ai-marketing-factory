from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas import RoleCreate, RoleUpdate, RoleResponse
from app.middleware import require_auth
from app.repositories.role import RoleRepository

router = APIRouter()
role_repo = RoleRepository()

ALLOWED_ROLE_PERMISSIONS = {
    "campaign:create",
    "campaign:edit",
    "campaign:delete",
    "campaign:read",
    "asset:create",
    "asset:edit",
    "asset:delete",
    "asset:read",
    "review:approve",
    "review:reject",
    "review:revision",
    "publish:execute",
    "member:manage",
    "role:manage",
}


def check_permission(payload: dict, permission: str) -> None:
    if permission not in (payload.get("permissions") or []):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def normalize_role_name(name: str) -> str:
    return " ".join(name.strip().split())


def validate_role_request(name: str | None, permissions: list[str] | None) -> tuple[str | None, list[str] | None]:
    normalized_name = normalize_role_name(name) if name is not None else None
    if name is not None and not normalized_name:
        raise HTTPException(status_code=422, detail="Role name is required")
    if normalized_name is not None and len(normalized_name) > 80:
        raise HTTPException(status_code=422, detail="Role name is too long")
    if permissions is None:
        return normalized_name, None
    deduped_permissions = list(dict.fromkeys(permissions))
    if any(permission not in ALLOWED_ROLE_PERMISSIONS for permission in deduped_permissions):
        raise HTTPException(status_code=422, detail="Invalid permissions")
    return normalized_name, deduped_permissions


@router.get("/roles", response_model=list[RoleResponse])
@router.get("/{company_id}/roles", response_model=list[RoleResponse])
async def list_roles(
    company_id: UUID,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "role:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot view roles of another company")

    roles = await role_repo.list_for_company(company_id)
    return [
        RoleResponse(
            role_id=r.role_id,
            company_id=r.company_id,
            name=r.name,
            is_system=r.is_system,
            permissions=r.permissions,
            created_at=str(r.created_at),
        )
        for r in roles
    ]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
@router.post("/{company_id}/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    company_id: UUID,
    req: RoleCreate,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "role:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot create roles for another company")

    role_name, role_permissions = validate_role_request(req.name, req.permissions)
    assert role_name is not None
    assert role_permissions is not None

    existing = await role_repo.get_by_name_for_company(company_id, role_name)
    if existing:
        raise HTTPException(status_code=409, detail="Role with this name already exists")

    role = await role_repo.create(company_id=company_id, name=role_name, permissions=role_permissions)
    return RoleResponse(
        role_id=role.role_id,
        company_id=role.company_id,
        name=role.name,
        is_system=role.is_system,
        permissions=role.permissions,
        created_at=str(role.created_at),
    )


@router.put("/roles/{role_id}", response_model=RoleResponse)
@router.put("/{company_id}/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    company_id: UUID,
    role_id: UUID,
    req: RoleUpdate,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "role:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot update roles of another company")

    role_name, role_permissions = validate_role_request(req.name, req.permissions)
    if role_name is not None:
        existing = await role_repo.get_by_name_for_company(company_id, role_name)
        if existing and existing.role_id != role_id:
            raise HTTPException(status_code=409, detail="Role with this name already exists")

    role = await role_repo.update(role_id, company_id=company_id, name=role_name, permissions=role_permissions)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or cannot update system role")
    return RoleResponse(
        role_id=role.role_id,
        company_id=role.company_id,
        name=role.name,
        is_system=role.is_system,
        permissions=role.permissions,
        created_at=str(role.created_at),
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{company_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    company_id: UUID,
    role_id: UUID,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "role:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot delete roles of another company")

    deleted = await role_repo.delete(role_id, company_id=company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Role not found or cannot delete system role")
