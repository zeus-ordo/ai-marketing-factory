import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_pool, close_pool, get_connection
from app.routes.auth import router as auth_router
from app.routes.company import router as company_router
from app.routes.roles import router as roles_router
from app.routes.platform import router as platform_router
from app.routes.invitation import router as invitation_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(init_pool, settings.MEMBERSHIP_DB_DSN)
    await ensure_optional_tables()
    yield
    await asyncio.to_thread(close_pool)


async def ensure_optional_tables() -> None:
    def _create_tables():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                # Base tables first (no FK dependencies)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS companies (
                        company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name TEXT NOT NULL,
                        slug TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS members (
                        member_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        company_id UUID REFERENCES companies(company_id) ON DELETE SET NULL,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS roles (
                        role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        company_id UUID REFERENCES companies(company_id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        is_system BOOLEAN NOT NULL DEFAULT FALSE,
                        permissions TEXT[] NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS member_roles (
                        member_id UUID NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
                        role_id UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
                        PRIMARY KEY (member_id, role_id)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS refresh_tokens (
                        token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        member_id UUID NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
                        token_hash TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        member_id UUID REFERENCES members(member_id) ON DELETE SET NULL,
                        company_id UUID REFERENCES companies(company_id) ON DELETE SET NULL,
                        action TEXT NOT NULL,
                        resource_type TEXT,
                        resource_id TEXT,
                        ip_address INET,
                        metadata JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                # Dependent tables (after base tables exist)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS invitations (
                        invitation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        company_id UUID NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
                        role_id UUID NOT NULL REFERENCES roles(role_id),
                        email TEXT NOT NULL,
                        token TEXT NOT NULL UNIQUE,
                        invited_by UUID REFERENCES members(member_id),
                        status TEXT NOT NULL DEFAULT 'pending',
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_verifications (
                        verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        member_id UUID NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
                        token TEXT NOT NULL UNIQUE,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS password_resets (
                        reset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        member_id UUID NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
                        token TEXT NOT NULL UNIQUE,
                        expires_at TIMESTAMPTZ NOT NULL,
                        used_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
    await asyncio.to_thread(_create_tables)


app = FastAPI(title="membership-service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(company_router, prefix="/api/v1/companies")
app.include_router(roles_router, prefix="/api/v1/companies")
app.include_router(platform_router, prefix="/api/v1")
app.include_router(invitation_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
