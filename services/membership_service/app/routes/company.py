from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas import MemberInviteRequest, MemberRoleUpdateRequest, MemberResponse, MemberListResponse, RoleResponse
from app.middleware import require_auth
from app.repositories.member import MemberRepository
from app.repositories.role import RoleRepository
from app.repositories.invitation import InvitationRepository
from app.services.email import send_email, EmailType
from app.config import settings
from app.permissions import require_any_permission, require_permission

router = APIRouter()
member_repo = MemberRepository()
role_repo = RoleRepository()
invitation_repo = InvitationRepository()


def check_permission(payload: dict, permission: str) -> None:
    require_permission(payload, permission)


async def get_member_roles(member_id: UUID) -> list[RoleResponse]:
    # Get roles from DB via member_roles join
    from app.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.role_id, r.company_id, r.name, r.is_system, r.permissions, r.created_at
                FROM roles r
                JOIN member_roles mr ON r.role_id = mr.role_id
                WHERE mr.member_id = %s
                """,
                (member_id,),
            )
            rows = cur.fetchall()
        return [
            RoleResponse(
                role_id=row["role_id"],
                company_id=row["company_id"],
                name=row["name"],
                is_system=row["is_system"],
                permissions=list(row["permissions"]) if row["permissions"] else [],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]


@router.post("/members/invite", status_code=status.HTTP_201_CREATED)
@router.post("/{company_id}/members/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    company_id: UUID,
    req: MemberInviteRequest,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "member:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot manage members of another company")

    role = await role_repo.get_by_id(req.role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.company_id is None:
        raise HTTPException(status_code=400, detail="Cannot assign platform roles")
    if str(role.company_id) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot assign roles from another company")

    inviter_id = UUID(payload["sub"])
    inv_id, token = await invitation_repo.create(
        company_id=company_id,
        role_id=req.role_id,
        email=req.email,
        invited_by=inviter_id,
    )

    invite_url = f"{settings.APP_BASE_URL}/auth/invite?token={token}"
    await send_email(
        to=req.email,
        subject=f"您被邀請加入",
        html_body=f'<p>您被邀請加入公司。點擊以下連結接受邀請：<a href="{invite_url}">{invite_url}</a></p>',
        email_type=EmailType.INVITATION,
    )
    return {"invitation_id": str(inv_id), "message": "Invitation sent"}


@router.get("/members", response_model=MemberListResponse)
@router.get("/{company_id}/members", response_model=MemberListResponse)
async def list_members(
    company_id: UUID,
    payload: dict = Depends(require_auth),
):
    require_any_permission(payload, "member:assign_role", "member:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot view members of another company")

    from app.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM members WHERE company_id = %s ORDER BY created_at DESC",
                (company_id,),
            )
            rows = cur.fetchall()
        items = []
        for row in rows:
            roles = await get_member_roles(row["member_id"])
            items.append(
                MemberResponse(
                    member_id=row["member_id"],
                    email=row["email"],
                    company_id=row["company_id"],
                    email_verified=row["email_verified"],
                    is_active=row["is_active"],
                    roles=roles,
                    created_at=str(row["created_at"]),
                )
            )
        return MemberListResponse(items=items, total=len(items))


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{company_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    company_id: UUID,
    member_id: UUID,
    payload: dict = Depends(require_auth),
):
    check_permission(payload, "member:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot remove members of another company")

    from app.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_id FROM members WHERE member_id = %s", (member_id,))
            target = cur.fetchone()
            if not target:
                raise HTTPException(status_code=404, detail="Member not found")
            if target["company_id"] is None or str(target["company_id"]) != str(company_id):
                raise HTTPException(status_code=403, detail="Cannot remove a member of another company")
            cur.execute(
                "UPDATE members SET company_id = NULL, is_active = FALSE WHERE member_id = %s AND company_id = %s",
                (member_id, company_id),
            )


@router.put("/members/{member_id}/roles")
@router.put("/{company_id}/members/{member_id}/roles")
async def update_member_roles(
    company_id: UUID,
    member_id: UUID,
    req: MemberRoleUpdateRequest,
    payload: dict = Depends(require_auth),
):
    require_any_permission(payload, "member:assign_role", "member:manage")
    if str(payload.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot update members of another company")

    target = await member_repo.get_by_id(member_id)
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.company_id is None or str(target.company_id) != str(company_id):
        raise HTTPException(status_code=403, detail="Cannot update a member of another company")

    role_ids = list(dict.fromkeys(req.role_ids))
    for role_id in role_ids:
        role = await role_repo.get_by_id(role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.is_system or role.company_id is None:
            raise HTTPException(status_code=422, detail="Cannot assign platform roles")
        if str(role.company_id) != str(company_id):
            raise HTTPException(status_code=403, detail="Cannot assign roles from another company")

    await role_repo.set_member_roles(
        member_id,
        role_ids,
        actor_id=UUID(payload["sub"]),
        company_id=company_id,
    )
    return {"message": "Roles updated"}
