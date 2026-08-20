import asyncio
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
        def _do():
            token = generate_secure_token()
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO invitations (company_id, role_id, email, token, invited_by, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING invitation_id
                        """,
                        (company_id, role_id, email, token, invited_by, expires_at),
                    )
                    row = cur.fetchone()
                    return row[0], token
        return await asyncio.to_thread(_do)

    async def get_by_token(self, token: str) -> dict | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT i.*, c.name as company_name, r.name as role_name
                        FROM invitations i
                        JOIN companies c ON i.company_id = c.company_id
                        JOIN roles r ON i.role_id = r.role_id
                        WHERE i.token = %s AND i.status = 'pending'
                        """,
                        (token,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    return dict(row)
        return await asyncio.to_thread(_do)

    async def accept(self, token: str) -> bool:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE invitations SET status = 'accepted' WHERE token = %s AND status = 'pending'",
                        (token,),
                    )
                    result = cur.fetchone()
                    return result is not None
        return await asyncio.to_thread(_do)

    async def cancel(self, token: str) -> bool:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE invitations SET status = 'cancelled' WHERE token = %s",
                        (token,),
                    )
                    result = cur.fetchone()
                    return result is not None
        return await asyncio.to_thread(_do)

    async def get_pending_by_email(self, email: str) -> list[dict]:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT i.*, c.name as company_name, r.name as role_name
                        FROM invitations i
                        JOIN companies c ON i.company_id = c.company_id
                        JOIN roles r ON i.role_id = r.role_id
                        WHERE i.email = %s AND i.status = 'pending'
                        """,
                        (email,),
                    )
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
        return await asyncio.to_thread(_do)
