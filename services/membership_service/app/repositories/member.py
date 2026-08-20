import asyncio
from uuid import UUID
from app.database import get_connection
from app.models import Member


class MemberRepository:
    async def create(self, email: str, password_hash: str, company_id: UUID | None) -> UUID:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    """
                    INSERT INTO members (email, password_hash, company_id)
                    VALUES (%s, %s, %s)
                    RETURNING member_id
                    """,
                    email,
                    password_hash,
                    company_id,
                )
                return row["member_id"]
        return await asyncio.to_thread(_do)

    async def get_by_email(self, email: str) -> Member | None:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    "SELECT * FROM members WHERE email = %s",
                    email,
                )
                if not row:
                    return None
                return Member(**dict(row))
        return await asyncio.to_thread(_do)

    async def get_by_id(self, member_id: UUID) -> Member | None:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    "SELECT * FROM members WHERE member_id = %s",
                    member_id,
                )
                if not row:
                    return None
                return Member(**dict(row))
        return await asyncio.to_thread(_do)

    async def verify_email(self, member_id: UUID) -> None:
        def _do():
            with get_connection() as conn:
                conn.execute(
                    "UPDATE members SET email_verified = TRUE WHERE member_id = %s",
                    member_id,
                )
        await asyncio.to_thread(_do)

    async def update_password(self, member_id: UUID, password_hash: str) -> None:
        def _do():
            with get_connection() as conn:
                conn.execute(
                    "UPDATE members SET password_hash = %s, updated_at = now() WHERE member_id = %s",
                    password_hash,
                    member_id,
                )
        await asyncio.to_thread(_do)

    async def set_active(self, member_id: UUID, is_active: bool) -> None:
        def _do():
            with get_connection() as conn:
                conn.execute(
                    "UPDATE members SET is_active = %s, updated_at = now() WHERE member_id = %s",
                    is_active,
                    member_id,
                )
        await asyncio.to_thread(_do)

    async def get_permissions(self, member_id: UUID) -> list[str]:
        def _do():
            with get_connection() as conn:
                rows = conn.fetch(
                    """
                    SELECT r.permissions
                    FROM roles r
                    JOIN member_roles mr ON r.role_id = mr.role_id
                    WHERE mr.member_id = %s
                    """,
                    member_id,
                )
            permissions: list[str] = []
            for row in rows:
                permissions.extend(row["permissions"] or [])
            return list(set(permissions))
        return await asyncio.to_thread(_do)
