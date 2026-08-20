from datetime import datetime, timedelta, timezone
from uuid import UUID
from app.config import settings
from app.repositories.member import MemberRepository
from app.repositories.token import RefreshTokenRepository
from app.utils.password import hash_password, verify_password
from app.utils.tokens import create_access_token, generate_secure_token
from app.services.email import send_email, EmailType

member_repo = MemberRepository()
token_repo = RefreshTokenRepository()


async def register_member(email: str, password: str) -> None:
    password_hash = hash_password(password)
    member_id = await member_repo.create(email=email, password_hash=password_hash, company_id=None)

    token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    async with __import__("app.database", fromlist=["get_connection"]).get_connection() as conn:
        await conn.execute(
            "INSERT INTO email_verifications (member_id, token, expires_at) VALUES ($1, $2, $3)",
            member_id,
            token,
            expires_at,
        )

    verify_url = f"{settings.APP_BASE_URL}/auth/verify-email?token={token}"
    await send_email(
        to=email,
        subject="驗證您的帳號",
        html_body=f'<p>請點擊以下連結驗證您的 Email：<a href="{verify_url}">{verify_url}</a></p>',
        email_type=EmailType.VERIFY,
    )


async def verify_email(token: str) -> bool:
    from app.database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT member_id FROM email_verifications WHERE token = $1 AND expires_at > now()",
            token,
        )
        if not row:
            return False
        member_id = row["member_id"]
        await member_repo.verify_email(member_id)
        await conn.execute("DELETE FROM email_verifications WHERE token = $1", token)
        return True


async def login_member(email: str, password: str) -> tuple[str, str] | None:
    member = await member_repo.get_by_email(email)
    if not member:
        return None
    if not member.email_verified or not member.is_active:
        return None
    if not verify_password(password, member.password_hash):
        return None

    permissions = await member_repo.get_permissions(member.member_id)

    access_payload = {
        "sub": str(member.member_id),
        "company_id": str(member.company_id) if member.company_id else None,
        "email": member.email,
        "permissions": permissions,
    }
    access_token = create_access_token(access_payload)

    refresh_token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_REFRESH_EXPIRY)
    # Allow multiple concurrent sessions for the same account. Each login gets
    # its own refresh token; logout/page-close revokes only that session token.
    await token_repo.store(member.member_id, refresh_token, expires_at)

    return access_token, refresh_token


async def refresh_access_token(refresh_token: str) -> tuple[str, str] | None:
    valid = await token_repo.validate(refresh_token)
    if not valid:
        return None

    member_id = await token_repo.get_member_id_by_token(refresh_token)
    if not member_id:
        return None

    member = await member_repo.get_by_id(member_id)
    permissions = await member_repo.get_permissions(member_id)
    access_payload = {
        "sub": str(member.member_id),
        "company_id": str(member.company_id) if member.company_id else None,
        "email": member.email,
        "permissions": permissions,
    }
    access_token = create_access_token(access_payload)

    # Keep the same refresh token on refresh. Rotating it here can log users out
    # unexpectedly when multiple tabs or visibility-change refreshes happen at the
    # same time: the first request revokes the token, and the second request then
    # fails with an invalid refresh token.
    return access_token, refresh_token


async def logout_member(refresh_token: str) -> None:
    await token_repo.revoke(refresh_token)


async def forgot_password(email: str) -> None:
    member = await member_repo.get_by_email(email)
    if not member or not member.email_verified:
        return
    token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    from app.database import get_connection
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO password_resets (member_id, token, expires_at) VALUES ($1, $2, $3)",
            member.member_id,
            token,
            expires_at,
        )
    reset_url = f"{settings.APP_BASE_URL}/auth/reset-password?token={token}"
    await send_email(
        to=email,
        subject="重置您的密碼",
        html_body=f'<p>點擊以下連結重置密碼（1小時內有效）：<a href="{reset_url}">{reset_url}</a></p>',
        email_type=EmailType.PASSWORD_RESET,
    )


async def reset_password(token: str, new_password: str) -> bool:
    from app.database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT member_id FROM password_resets WHERE token = $1 AND used_at IS NULL AND expires_at > now()",
            token,
        )
        if not row:
            return False
        member_id = row["member_id"]
        password_hash = hash_password(new_password)
        await member_repo.update_password(member_id, password_hash)
        await token_repo.revoke_all_for_member(member_id)
        await conn.execute(
            "UPDATE password_resets SET used_at = now() WHERE token = $1",
            token,
        )
        return True


async def get_current_member(member_id: str) -> dict | None:
    member = await member_repo.get_by_id(UUID(member_id))
    if not member:
        return None
    permissions = await member_repo.get_permissions(member.member_id)
    return {
        "member_id": member.member_id,
        "email": member.email,
        "company_id": member.company_id,
        "permissions": permissions,
    }
