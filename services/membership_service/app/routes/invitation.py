from fastapi import APIRouter, HTTPException, status
from app.schemas import InvitationAcceptRequest, InvitationResponse, AuthResponse
from app.repositories.invitation import InvitationRepository
from app.repositories.member import MemberRepository
from app.repositories.role import RoleRepository
from app.utils.password import hash_password
from app.utils.tokens import create_access_token, generate_secure_token
from app.config import settings
from datetime import datetime, timedelta, timezone

router = APIRouter()
invitation_repo = InvitationRepository()
member_repo = MemberRepository()
role_repo = RoleRepository()


@router.get("/invitation/accept", response_model=InvitationResponse)
async def get_invitation(token: str):
    inv = await invitation_repo.get_by_token(token)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")
    if inv["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")
    return InvitationResponse(
        invitation_id=inv["invitation_id"],
        company_name=inv["company_name"],
        role_name=inv["role_name"],
        email=inv["email"],
        status=inv["status"],
        expires_at=str(inv["expires_at"]),
    )


@router.post("/invitation/accept", response_model=AuthResponse)
async def accept_invitation(req: InvitationAcceptRequest, token: str):
    inv = await invitation_repo.get_by_token(token)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")
    if inv["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")

    password_hash = hash_password(req.password)
    member_id = await member_repo.create(
        email=inv["email"],
        password_hash=password_hash,
        company_id=inv["company_id"],
    )

    # Verify and assign role
    from app.database import get_connection
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE members SET email_verified = TRUE WHERE member_id = $1",
            member_id,
        )

    await role_repo.assign_to_member(member_id, inv["role_id"])
    await invitation_repo.accept(token)

    permissions = await member_repo.get_permissions(member_id)
    access_payload = {
        "sub": str(member_id),
        "company_id": str(inv["company_id"]),
        "email": inv["email"],
        "permissions": permissions,
    }
    access_token = create_access_token(access_payload)
    refresh_token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_REFRESH_EXPIRY)
    from app.repositories.token import RefreshTokenRepository
    token_repo = RefreshTokenRepository()
    await token_repo.store(member_id, refresh_token, expires_at)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
    )
