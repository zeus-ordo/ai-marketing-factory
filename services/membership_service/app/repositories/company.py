import asyncio
from uuid import UUID
from app.database import get_connection
from app.models import Company


class CompanyRepository:
    async def create(self, name: str, slug: str) -> Company:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    """
                    INSERT INTO companies (name, slug)
                    VALUES (%s, %s)
                    RETURNING *
                    """,
                    name,
                    slug,
                )
                return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def get_by_id(self, company_id: UUID) -> Company | None:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    "SELECT * FROM companies WHERE company_id = %s",
                    company_id,
                )
                if not row:
                    return None
                return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def get_by_slug(self, slug: str) -> Company | None:
        def _do():
            with get_connection() as conn:
                row = conn.fetchrow(
                    "SELECT * FROM companies WHERE slug = %s",
                    slug,
                )
                if not row:
                    return None
                return Company(**dict(row))
        return await asyncio.to_thread(_do)

    async def list_all(self) -> list[Company]:
        def _do():
            with get_connection() as conn:
                rows = conn.fetch("SELECT * FROM companies ORDER BY created_at DESC")
                return [Company(**dict(row)) for row in rows]
        return await asyncio.to_thread(_do)

    async def delete(self, company_id: UUID) -> bool:
        def _do():
            with get_connection() as conn:
                result = conn.execute(
                    "DELETE FROM companies WHERE company_id = %s",
                    company_id,
                )
                return result == "DELETE 1"
        return await asyncio.to_thread(_do)
