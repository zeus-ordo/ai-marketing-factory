import asyncio
from uuid import UUID
from app.database import get_connection
from app.models import Company


class CompanyRepository:
    async def create(self, name: str, slug: str) -> Company:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO companies (name, slug)
                        VALUES (%s, %s)
                        RETURNING *
                        """,
                        (name, slug),
                    )
                    row = cur.fetchone()
                    return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def get_by_id(self, company_id: UUID) -> Company | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def get_by_slug(self, slug: str) -> Company | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM companies WHERE slug = %s", (slug,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def list_all(self) -> list[Company]:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM companies ORDER BY created_at DESC")
                    rows = cur.fetchall()
                    return [Company(**dict(row)) for row in rows]
        return await asyncio.to_thread(_do)

    async def delete(self, company_id: UUID) -> bool:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM companies WHERE company_id = %s", (company_id,))
                    result = cur.fetchone()
                    return result is not None
        return await asyncio.to_thread(_do)
