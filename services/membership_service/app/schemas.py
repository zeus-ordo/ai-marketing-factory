from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class MemberProfile(BaseModel):
    member_id: UUID
    email: str
    company_id: Optional[UUID]
    permissions: list[str]


# ─── Company ─────────────────────────────────────────────────────────────────

class CompanyCreate(BaseModel):
    name: str
    slug: str


class CompanyResponse(BaseModel):
    company_id: UUID
    name: str
    slug: str
    created_at: str
    updated_at: str


# ─── Roles ───────────────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    permissions: list[str]


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[list[str]] = None


class RoleResponse(BaseModel):
    role_id: UUID
    company_id: Optional[UUID]
    name: str
    is_system: bool
    permissions: list[str]
    created_at: str


# ─── Members ──────────────────────────────────────────────────────────────────

class MemberInviteRequest(BaseModel):
    email: EmailStr
    role_id: UUID


class MemberRoleUpdateRequest(BaseModel):
    role_ids: list[UUID]


class MemberResponse(BaseModel):
    member_id: UUID
    email: str
    company_id: Optional[UUID]
    email_verified: bool
    is_active: bool
    roles: list[RoleResponse]
    created_at: str


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
    total: int


# ─── Invitation ───────────────────────────────────────────────────────────────

class InvitationAcceptRequest(BaseModel):
    password: str


class InvitationResponse(BaseModel):
    invitation_id: UUID
    company_name: str
    role_name: str
    email: str
    status: str
    expires_at: str


# ─── Developer Admin ───────────────────────────────────────────────────────────

class CreateCompanyAdminRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformCompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int


# ─── Audit Logs ───────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    log_id: UUID
    member_id: UUID | None
    company_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    metadata: dict | None
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
