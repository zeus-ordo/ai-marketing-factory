from uuid import UUID
from app.database import get_connection
from app.models import Member


class MemberRepository:
    async def create(self, email: str, password_hash: str, company_id: UUID | None) -> UUID:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO members (email, password_hash, company_id)
                VALUES ($1, $2, $3)
                RETURNING member_id
                """,
                email,
                password_hash,
                company_id,
            )
            return row["member_id"]

    async def get_by_email(self, email: str) -> Member | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM members WHERE email = $1",
                email,
            )
            if not row:
                return None
            return Member(**dict(row))

    async def get_by_id(self, member_id: UUID) -> Member | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM members WHERE member_id = $1",
                member_id,
            )
            if not row:
                return None
            return Member(**dict(row))

    async def verify_email(self, member_id: UUID) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE members SET email_verified = TRUE WHERE member_id = $1",
                member_id,
            )

    async def update_password(self, member_id: UUID, password_hash: str) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE members SET password_hash = $1, updated_at = now() WHERE member_id = $2",
                password_hash,
                member_id,
            )

    async def set_active(self, member_id: UUID, is_active: bool) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE members SET is_active = $1, updated_at = now() WHERE member_id = $2",
                is_active,
                member_id,
            )

    async def get_permissions(self, member_id: UUID) -> list[str]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT r.permissions
                FROM roles r
                JOIN member_roles mr ON r.role_id = mr.role_id
                WHERE mr.member_id = $1
                """,
                member_id,
            )
            permissions: list[str] = []
            for row in rows:
                permissions.extend(row["permissions"] or [])
            return list(set(permissions))
