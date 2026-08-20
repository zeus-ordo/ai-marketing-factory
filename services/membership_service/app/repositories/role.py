import asyncio
from uuid import UUID
from app.database import get_connection
from app.models import Role


class RoleRepository:
    async def get_by_id(self, role_id: UUID) -> Role | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM roles WHERE role_id = %s", (role_id,))
                    row = cur.fetchone()
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
        return await asyncio.to_thread(_do)

    async def get_by_name_for_company(self, company_id: UUID | None, name: str) -> Role | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    if company_id is None:
                        cur.execute(
                            "SELECT * FROM roles WHERE company_id IS NULL AND name = %s",
                            (name,),
                        )
                    else:
                        cur.execute(
                            "SELECT * FROM roles WHERE company_id = %s AND name = %s",
                            (company_id, name),
                        )
                    row = cur.fetchone()
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
        return await asyncio.to_thread(_do)

    async def list_for_company(self, company_id: UUID) -> list[Role]:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM roles WHERE company_id = %s OR company_id IS NULL ORDER BY is_system DESC, name",
                        (company_id,),
                    )
                    rows = cur.fetchall()
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
        return await asyncio.to_thread(_do)

    async def create(self, company_id: UUID | None, name: str, permissions: list[str]) -> Role:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO roles (company_id, name, is_system, permissions)
                        VALUES (%s, %s, FALSE, %s)
                        RETURNING *
                        """,
                        (company_id, name, permissions),
                    )
                    row = cur.fetchone()
                    return Role(
                        role_id=row["role_id"],
                        company_id=row["company_id"],
                        name=row["name"],
                        is_system=row["is_system"],
                        permissions=list(row["permissions"]) if row["permissions"] else [],
                        created_at=row["created_at"],
                    )
        return await asyncio.to_thread(_do)

    async def update(self, role_id: UUID, company_id: UUID, name: str | None, permissions: list[str] | None) -> Role | None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM roles WHERE role_id = %s", (role_id,))
                    current = cur.fetchone()
                    if not current or current["is_system"] or str(current["company_id"]) != str(company_id):
                        return None
                    new_name = name if name is not None else current["name"]
                    new_perms = permissions if permissions is not None else list(current["permissions"])
                    cur.execute(
                        """
                        UPDATE roles SET name = %s, permissions = %s
                        WHERE role_id = %s
                        RETURNING *
                        """,
                        (new_name, new_perms, role_id),
                    )
                    row = cur.fetchone()
                    return Role(
                        role_id=row["role_id"],
                        company_id=row["company_id"],
                        name=row["name"],
                        is_system=row["is_system"],
                        permissions=list(row["permissions"]) if row["permissions"] else [],
                        created_at=row["created_at"],
                    )
        return await asyncio.to_thread(_do)

    async def delete(self, role_id: UUID, company_id: UUID) -> bool:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM roles WHERE role_id = %s AND company_id = %s AND is_system = FALSE",
                        (role_id, company_id),
                    )
                    result = cur.fetchone()
                    return result is not None
        return await asyncio.to_thread(_do)

    async def assign_to_member(self, member_id: UUID, role_id: UUID) -> None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO member_roles (member_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (member_id, role_id),
                    )
        await asyncio.to_thread(_do)

    async def remove_from_member(self, member_id: UUID, role_id: UUID) -> None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM member_roles WHERE member_id = %s AND role_id = %s",
                        (member_id, role_id),
                    )
        await asyncio.to_thread(_do)

    async def set_member_roles(self, member_id: UUID, role_ids: list[UUID]) -> None:
        def _do():
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM member_roles WHERE member_id = %s", (member_id,))
                    for role_id in role_ids:
                        cur.execute(
                            "INSERT INTO member_roles (member_id, role_id) VALUES (%s, %s)",
                            (member_id, role_id),
                        )
        await asyncio.to_thread(_do)
