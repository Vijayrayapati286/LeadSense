"""Authentication routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import AuthCallbackResponse, DevLoginRequest, PasswordLoginRequest, UserResponse
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()
settings = get_settings()


@router.get("/login")
def login():
    """Get Microsoft SSO login URL."""
    return auth_service.get_login_url()


@router.get("/callback")
def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Handle Microsoft OAuth callback and redirect to frontend."""
    try:
        result = auth_service.handle_callback(code, state, db)
        redirect_url = (
            f"{settings.frontend_url}/auth/callback"
            f"?token={result['access_token']}"
        )
        return RedirectResponse(url=redirect_url)
    except Exception as exc:
        logger.error("Auth callback failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/login?error=auth_failed"
        )


@router.post("/dev-login", response_model=AuthCallbackResponse)
def dev_login(data: DevLoginRequest | None = None, db: Session = Depends(get_db)):
    """Development login when Azure AD is not configured.

    Accepts an optional email/name so multiple team members can simulate
    distinct sender identities locally before real Azure AD SSO is wired up.
    """
    kwargs = {}
    if data and data.email:
        kwargs["email"] = data.email
    if data and data.name:
        kwargs["name"] = data.name

    result = auth_service.dev_login(db, **kwargs)
    return AuthCallbackResponse(
        access_token=result["access_token"],
        user=UserResponse.model_validate(result["user"]),
    )


@router.post("/login", response_model=AuthCallbackResponse)
def password_login(data: PasswordLoginRequest, db: Session = Depends(get_db)):
    """Email+password login for named team members (see provision_core_users) —
    distinct from both real Azure AD SSO and the unauthenticated dev-login
    fallback used before real accounts exist."""
    try:
        result = auth_service.password_login(db, data.email, data.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return AuthCallbackResponse(
        access_token=result["access_token"],
        user=UserResponse.model_validate(result["user"]),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout():
    """Logout endpoint (client-side token removal)."""
    return {"message": "Logged out successfully", "success": True}
