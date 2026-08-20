import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.schemas import (
    RegisterRequest,
    VerifyEmailRequest,
    LoginRequest,
    RefreshRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    AuthResponse,
    MemberProfile,
)
from app.services.auth import (
    register_member,
    verify_email,
    login_member,
    refresh_access_token,
    logout_member,
    forgot_password,
    reset_password,
    get_current_member,
)
from app.middleware import require_auth

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    try:
        await register_member(req.email, req.password)
    except Exception:
        pass
    return {"message": "Registration successful. Please check your email to verify."}


@router.post("/verify-email")
async def verify(req: VerifyEmailRequest):
    success = await verify_email(req.token)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {"message": "Email verified successfully"}


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    result = await login_member(req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token, refresh_token = result
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest):
    result = await refresh_access_token(req.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    access_token, new_refresh = result
    return AuthResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=3600,
    )


@router.post("/logout")
async def logout(req: RefreshRequest):
    if req.refresh_token:
        await logout_member(req.refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/logout-beacon")
async def logout_beacon(request: Request):
    raw = (await request.body()).decode("utf-8", errors="ignore").strip()
    refresh_token = ""
    if raw:
        try:
            payload = json.loads(raw)
            refresh_token = str(payload.get("refresh_token") or "")
        except json.JSONDecodeError:
            refresh_token = raw
    if refresh_token:
        await logout_member(refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot(req: ForgotPasswordRequest):
    await forgot_password(req.email)
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset(req: ResetPasswordRequest):
    success = await reset_password(req.token, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {"message": "Password reset successfully"}


@router.get("/me", response_model=MemberProfile)
async def me(payload: dict = Depends(require_auth)):
    profile = await get_current_member(payload["sub"])
    if not profile:
        raise HTTPException(status_code=404, detail="Member not found")
    return MemberProfile(**profile)
