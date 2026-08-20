import json as _json
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Header, Query
from app.schemas import (
    CompanyCreate,
    CompanyResponse,
    CreateCompanyAdminRequest,
    PlatformCompanyListResponse,
    MemberListResponse,
    MemberResponse,
    RoleResponse,
    AuditLogListResponse,
    AuditLogEntry,
)
from app.repositories.company import CompanyRepository
from app.repositories.member import MemberRepository
from app.repositories.role import RoleRepository
from app.utils.password import hash_password
from app.config import settings
from app.database import get_connection

router = APIRouter()
company_repo = CompanyRepository()
member_repo = MemberRepository()
role_repo = RoleRepository()

def require_developer(x_platform_key: str = Header(...)) -> dict:
    if x_platform_key != settings.PLATFORM_ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"role": "developer"}


@router.post("/platform/companies", response_model=CompanyResponse, status_code=201)
async def create_company(
    req: CompanyCreate,
    _: dict = Depends(require_developer),
):
    existing = await company_repo.get_by_slug(req.slug)
    if existing:
        raise HTTPException(status_code=409, detail="Company with this slug already exists")
    company = await company_repo.create(name=req.name, slug=req.slug)

    # Write audit log for company creation
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO audit_logs (member_id, company_id, action, resource_type, resource_id, metadata)
            VALUES (NULL, $1, $2, $3, $4, $5)
            """,
            company.company_id,
            "company.create",
            "company",
            str(company.company_id),
            _json.dumps({"name": company.name, "slug": company.slug}),
        )

    return CompanyResponse(
        company_id=company.company_id,
        name=company.name,
        slug=company.slug,
        created_at=str(company.created_at),
        updated_at=str(company.updated_at),
    )


@router.get("/platform/companies", response_model=PlatformCompanyListResponse)
async def list_companies(_: dict = Depends(require_developer)):
    companies = await company_repo.list_all()
    return PlatformCompanyListResponse(
        items=[
            CompanyResponse(
                company_id=c.company_id,
                name=c.name,
                slug=c.slug,
                created_at=str(c.created_at),
                updated_at=str(c.updated_at),
            )
            for c in companies
        ],
        total=len(companies),
    )


@router.post("/platform/companies/{company_id}/admin", status_code=201)
async def create_company_admin(
    company_id: UUID,
    req: CreateCompanyAdminRequest,
    _: dict = Depends(require_developer),
):
    company = await company_repo.get_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    existing = await member_repo.get_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Member with this email already exists")

    password_hash = hash_password(req.password)
    member_id = await member_repo.create(
        email=req.email,
        password_hash=password_hash,
        company_id=company_id,
    )

    # Auto-verify email for admin created by developer
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE members SET email_verified = TRUE WHERE member_id = $1",
            member_id,
        )

    # Assign company_admin role
    admin_role = await role_repo.get_by_id(UUID("00000000-0000-0000-0000-000000000001"))
    if admin_role:
        await role_repo.assign_to_member(member_id, admin_role.role_id)

    return {"member_id": str(member_id), "message": "Company admin created"}


@router.get("/platform/companies/{company_id}/members", response_model=MemberListResponse)
async def get_company_members(
    company_id: UUID,
    _: dict = Depends(require_developer),
):
    company = await company_repo.get_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM members WHERE company_id = $1 ORDER BY created_at DESC",
            company_id,
        )
        items = []
        for row in rows:
            role_rows = await conn.fetch(
                """
                SELECT r.role_id, r.company_id, r.name, r.is_system, r.permissions, r.created_at
                FROM roles r
                JOIN member_roles mr ON r.role_id = mr.role_id
                WHERE mr.member_id = $1
                """,
                row["member_id"],
            )
            roles = [
                RoleResponse(
                    role_id=r["role_id"],
                    company_id=r["company_id"],
                    name=r["name"],
                    is_system=r["is_system"],
                    permissions=list(r["permissions"]) if r["permissions"] else [],
                    created_at=str(r["created_at"]),
                )
                for r in role_rows
            ]
            items.append(
                MemberResponse(
                    member_id=row["member_id"],
                    email=row["email"],
                    company_id=row["company_id"],
                    email_verified=row["email_verified"],
                    is_active=row["is_active"],
                    roles=roles,
                    created_at=str(row["created_at"]),
                )
            )
        return MemberListResponse(items=items, total=len(items))


@router.get("/platform/members", response_model=MemberListResponse)
async def list_all_members(_: dict = Depends(require_developer)):
    async with get_connection() as conn:
        rows = await conn.fetch("SELECT * FROM members ORDER BY created_at DESC")
        items = []
        for row in rows:
            role_rows = await conn.fetch(
                """
                SELECT r.role_id, r.company_id, r.name, r.is_system, r.permissions, r.created_at
                FROM roles r
                JOIN member_roles mr ON r.role_id = mr.role_id
                WHERE mr.member_id = $1
                """,
                row["member_id"],
            )
            roles = [
                RoleResponse(
                    role_id=r["role_id"],
                    company_id=r["company_id"],
                    name=r["name"],
                    is_system=r["is_system"],
                    permissions=list(r["permissions"]) if r["permissions"] else [],
                    created_at=str(r["created_at"]),
                )
                for r in role_rows
            ]
            items.append(
                MemberResponse(
                    member_id=row["member_id"],
                    email=row["email"],
                    company_id=row["company_id"],
                    email_verified=row["email_verified"],
                    is_active=row["is_active"],
                    roles=roles,
                    created_at=str(row["created_at"]),
                )
            )
        return MemberListResponse(items=items, total=len(items))


@router.get("/platform/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    _: dict = Depends(require_developer),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    member_id: UUID | None = None,
    company_id: UUID | None = None,
):
    """List audit logs with optional filters. Requires platform admin key."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        conditions = []
        params: list = []
        param_idx = 1

        if action:
            conditions.append(f"action = ${param_idx}")
            params.append(action)
            param_idx += 1

        if member_id:
            conditions.append(f"member_id = ${param_idx}")
            params.append(member_id)
            param_idx += 1

        if company_id:
            conditions.append(f"company_id = ${param_idx}")
            params.append(company_id)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        count_query = f"SELECT COUNT(*) as total FROM audit_logs {where_clause}"
        count_row = await conn.fetchrow(count_query, *params)
        total = count_row["total"] if count_row else 0

        query = f"""
            SELECT log_id, member_id, company_id, action,
                   resource_type, resource_id, ip_address, metadata, created_at
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])
        rows = await conn.fetch(query, *params)

        items = [
            AuditLogEntry(
                log_id=row["log_id"],
                member_id=row["member_id"],
                company_id=row["company_id"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                ip_address=str(row["ip_address"]) if row["ip_address"] else None,
                metadata=_json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or None),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

        return AuditLogListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
