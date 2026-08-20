from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Company:
    company_id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Member:
    member_id: UUID
    company_id: UUID | None
    email: str
    password_hash: str
    email_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class Role:
    role_id: UUID
    company_id: UUID | None
    name: str
    is_system: bool
    permissions: list[str]
    created_at: datetime


@dataclass
class RefreshTokenRecord:
    token_id: UUID
    member_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
