import asyncio
from uuid import UUID
from datetime import datetime, timezone
from app.database import get_connection
from app.utils.tokens import hash_token, verify_token


class RefreshTokenRepository:
    async def store(self, member_id: UUID, token: str, expires_at: datetime) -> UUID:
        def _do():
            token_hash = hash_token(token)
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO refresh_tokens (member_id, token_hash, expires_at)
                        VALUES (%s, %s, %s)
                        RETURNING token_id
                        """,
                        (member_id, token_hash, expires_at),
                    )
                    row = cur.fetchone()
                    return row["token_id"] if row else None
        return await asyncio.to_thread(_do)

    async def validate(self, token: str) -> bool:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT token_hash FROM refresh_tokens
                        WHERE revoked_at IS NULL
                          AND expires_at > now()
                        """,
                    )
                    rows = cur.fetchall()
                    return any(verify_token(token, row["token_hash"]) for row in rows)
        return await asyncio.to_thread(_do)

    async def revoke(self, token: str) -> None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT token_id, token_hash FROM refresh_tokens
                        WHERE revoked_at IS NULL
                          AND expires_at > now()
                        """,
                    )
                    rows = cur.fetchall()
                    matching_ids = [row["token_id"] for row in rows if verify_token(token, row["token_hash"])]
                    if matching_ids:
                        cur.execute(
                            "UPDATE refresh_tokens SET revoked_at = now() WHERE token_id = ANY(%s::uuid[])",
                            (matching_ids,),
                        )
        await asyncio.to_thread(_do)

    async def revoke_all_for_member(self, member_id: UUID) -> None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE refresh_tokens
                        SET revoked_at = now()
                        WHERE member_id = %s AND revoked_at IS NULL
                        """,
                        (member_id,),
                    )
        await asyncio.to_thread(_do)

    async def get_member_id_by_token(self, token: str) -> UUID | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT member_id, token_hash FROM refresh_tokens
                        WHERE revoked_at IS NULL AND expires_at > now()
                        """,
                    )
                    rows = cur.fetchall()
                    for row in rows:
                        if verify_token(token, row["token_hash"]):
                            return row["member_id"]
                    return None
        return await asyncio.to_thread(_do)
