from uuid import UUID
from app.database import get_connection
from app.models import Role


class RoleRepository:
    async def get_by_id(self, role_id: UUID) -> Role | None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM roles WHERE role_id = $1",
                role_id,
            )
            if not row:
                return None
            return Role(
                role_id=row["role_id"],
                company_id=row["company_id"],
                name=row["name"],
                is_system=row["is_system"],
                permissions=list(row["permissions"]) if row["permissions"] else [],
                created_at=row["created_at"],
            )

    async def get_by_name_for_company(self, company_id: UUID | None, name: str) -> Role | None:
        async with get_connection() as conn:
            if company_id is None:
                row = await conn.fetchrow(
                    "SELECT * FROM roles WHERE company_id IS NULL AND name = $1",
                    name,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM roles WHERE company_id = $1 AND name = $2",
                    company_id,
                    name,
                )
            if not row:
                return None
            return Role(
                role_id=row["role_id"],
                company_id=row["company_id"],
                name=row["name"],
                is_system=row["is_system"],
                permissions=list(row["permissions"]) if row["permissions"] else [],
                created_at=row["created_at"],
            )

    async def list_for_company(self, company_id: UUID) -> list[Role]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM roles WHERE company_id = $1 OR company_id IS NULL ORDER BY is_system DESC, name",
                company_id,
            )
            return [
                Role(
                    role_id=row["role_id"],
                    company_id=row["company_id"],
                    name=row["name"],
                    is_system=row["is_system"],
                    permissions=list(row["permissions"]) if row["permissions"] else [],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def create(self, company_id: UUID | None, name: str, permissions: list[str]) -> Role:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO roles (company_id, name, is_system, permissions)
                VALUES ($1, $2, FALSE, $3)
                RETURNING *
                """,
                company_id,
                name,
                permissions,
            )
            return Role(
                role_id=row["role_id"],
                company_id=row["company_id"],
                name=row["name"],
                is_system=row["is_system"],
                permissions=list(row["permissions"]) if row["permissions"] else [],
                created_at=row["created_at"],
            )

    async def update(self, role_id: UUID, company_id: UUID, name: str | None, permissions: list[str] | None) -> Role | None:
        async with get_connection() as conn:
            current = await conn.fetchrow("SELECT * FROM roles WHERE role_id = $1", role_id)
            if not current or current["is_system"] or str(current["company_id"]) != str(company_id):
                return None
            new_name = name if name is not None else current["name"]
            new_perms = permissions if permissions is not None else list(current["permissions"])
            row = await conn.fetchrow(
                """
                UPDATE roles SET name = $2, permissions = $3
                WHERE role_id = $1
                RETURNING *
                """,
                role_id,
                new_name,
                new_perms,
            )
            return Role(
                role_id=row["role_id"],
                company_id=row["company_id"],
                name=row["name"],
                is_system=row["is_system"],
                permissions=list(row["permissions"]) if row["permissions"] else [],
                created_at=row["created_at"],
            )

    async def delete(self, role_id: UUID, company_id: UUID) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM roles WHERE role_id = $1 AND company_id = $2 AND is_system = FALSE",
                role_id,
                company_id,
            )
            return result == "DELETE 1"

    async def assign_to_member(self, member_id: UUID, role_id: UUID) -> None:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO member_roles (member_id, role_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                member_id,
                role_id,
            )

    async def remove_from_member(self, member_id: UUID, role_id: UUID) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM member_roles WHERE member_id = $1 AND role_id = $2",
                member_id,
                role_id,
            )

    async def set_member_roles(self, member_id: UUID, role_ids: list[UUID]) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM member_roles WHERE member_id = $1",
                member_id,
            )
            for role_id in role_ids:
                await conn.execute(
                    "INSERT INTO member_roles (member_id, role_id) VALUES ($1, $2)",
                    member_id,
                    role_id,
                )
