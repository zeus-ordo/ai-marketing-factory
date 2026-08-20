from uuid import UUID
from app.database import get_connection
from app.models import Company


class CompanyRepository:
    async def create(self, name: str, slug: str) -> Company:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO companies (name, slug)
                VALUES ($1, $2)
                RETURNING *
                """,
                name,
                slug,
            )
            return Company(**dict(row))

    async def get_by_id(self, company_id: UUID) -> Company | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM companies WHERE company_id = $1",
                company_id,
            )
            if not row:
                return None
            return Company(**dict(row))

    async def get_by_slug(self, slug: str) -> Company | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM companies WHERE slug = $1",
                slug,
            )
            if not row:
                return None
            return Company(**dict(row))

    async def list_all(self) -> list[Company]:
        async with get_connection() as conn:
            rows = await conn.fetch("SELECT * FROM companies ORDER BY created_at DESC")
            return [Company(**dict(row)) for row in rows]

    async def delete(self, company_id: UUID) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM companies WHERE company_id = $1",
                company_id,
            )
            return result == "DELETE 1"
