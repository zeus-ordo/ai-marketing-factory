from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.database import get_connection
from app.utils.tokens import generate_secure_token


class InvitationRepository:
    async def create(
        self,
        company_id: UUID,
        role_id: UUID,
        email: str,
        invited_by: UUID,
        expires_days: int = 7,
    ) -> tuple[UUID, str]:
        token = generate_secure_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO invitations (company_id, role_id, email, token, invited_by, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING invitation_id
                """,
                company_id,
                role_id,
                email,
                token,
                invited_by,
                expires_at,
            )
            return row["invitation_id"], token

    async def get_by_token(self, token: str) -> dict | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT i.*, c.name as company_name, r.name as role_name
                FROM invitations i
                JOIN companies c ON i.company_id = c.company_id
                JOIN roles r ON i.role_id = r.role_id
                WHERE i.token = $1 AND i.status = 'pending'
                """,
                token,
            )
            if not row:
                return None
            return dict(row)

    async def accept(self, token: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                "UPDATE invitations SET status = 'accepted' WHERE token = $1 AND status = 'pending'",
                token,
            )
            return result == "UPDATE 1"

    async def cancel(self, token: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                "UPDATE invitations SET status = 'cancelled' WHERE token = $1",
                token,
            )
            return result == "UPDATE 1"

    async def get_pending_by_email(self, email: str) -> list[dict]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT i.*, c.name as company_name, r.name as role_name
                FROM invitations i
                JOIN companies c ON i.company_id = c.company_id
                JOIN roles r ON i.role_id = r.role_id
                WHERE i.email = $1 AND i.status = 'pending'
                """,
                email,
            )
            return [dict(row) for row in rows]
