from uuid import UUID
from datetime import datetime, timezone
from app.database import get_connection
from app.utils.tokens import hash_token, verify_token


class RefreshTokenRepository:
    async def store(self, member_id: UUID, token: str, expires_at: datetime) -> UUID:
        token_hash = hash_token(token)
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO refresh_tokens (member_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                RETURNING token_id
                """,
                member_id,
                token_hash,
                expires_at,
            )
            return row["token_id"]

    async def validate(self, token: str) -> bool:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT token_hash FROM refresh_tokens
                WHERE revoked_at IS NULL
                  AND expires_at > now()
                """,
            )
            return any(verify_token(token, row["token_hash"]) for row in rows)

    async def revoke(self, token: str) -> None:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT token_id, token_hash FROM refresh_tokens
                WHERE revoked_at IS NULL
                  AND expires_at > now()
                """,
            )
            matching_ids = [row["token_id"] for row in rows if verify_token(token, row["token_hash"])]
            if matching_ids:
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked_at = now() WHERE token_id = ANY($1::uuid[])",
                    matching_ids,
                )

    async def revoke_all_for_member(self, member_id: UUID) -> None:
        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE refresh_tokens
                SET revoked_at = now()
                WHERE member_id = $1 AND revoked_at IS NULL
                """,
                member_id,
            )

    async def get_member_id_by_token(self, token: str) -> UUID | None:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT member_id, token_hash FROM refresh_tokens
                WHERE revoked_at IS NULL AND expires_at > now()
                """,
            )
            for row in rows:
                if verify_token(token, row["token_hash"]):
                    return row["member_id"]
            return None
