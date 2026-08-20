import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

PLATFORM_ADMIN_KEY = os.getenv("PLATFORM_ADMIN_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"


class JWTPayload(BaseModel):
    """JWT Access Token payload — mirrors membership service token structure."""

    sub: str  # member_id
    company_id: str | None
    email: str
    permissions: list[str]
    exp: int
    iat: int


def get_token_from_request(req: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = req.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def decode_jwt(token: str) -> JWTPayload:
    """Decode and validate a JWT. Raises 401 on failure."""
    if not JWT_SECRET:
        raise HTTPException(status_code=503, detail="JWT_SECRET not configured on campaign service")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return JWTPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def is_platform_admin_request(req: Request) -> bool:
    """Check if request carries a valid platform admin key."""
    if not PLATFORM_ADMIN_KEY:
        return False
    key = req.headers.get("x-platform-key", "")
    return bool(key) and key == PLATFORM_ADMIN_KEY


# --- FastAPI Dependencies ---


def require_jwt(req: Request) -> JWTPayload:
    """Require a valid JWT. Raises 401 if missing or invalid."""
    token = get_token_from_request(req)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return decode_jwt(token)


def optional_jwt(req: Request) -> JWTPayload | None:
    """Validate JWT if present, return None if missing. Raises 401 if invalid."""
    token = get_token_from_request(req)
    if token is None:
        return None
    return decode_jwt(token)


def require_platform_admin(req: Request) -> bool:
    """Require a valid platform admin key. Raises 403 if invalid."""
    if not is_platform_admin_request(req):
        raise HTTPException(status_code=403, detail="Invalid platform key")
    return True


def check_permission(payload: JWTPayload, permission: str) -> None:
    """Check if the JWT payload grants the required permission. Raises 403 if not."""
    if payload.permissions == ["*"]:
        return  # superuser
    if permission not in payload.permissions:
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission} required")


# Type alias for use in route signatures
JWTDep = Annotated[JWTPayload, Depends(require_jwt)]
OptJWTDep = Annotated[JWTPayload | None, Depends(optional_jwt)]
PlatformAdminDep = Annotated[bool, Depends(require_platform_admin)]
