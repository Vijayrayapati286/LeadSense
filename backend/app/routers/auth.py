"""Authentication routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.middleware.pat_auth import get_raw_bearer, security as bearer_security, try_pat_principal, whoami_response
from app.models import User
from app.schemas.schemas import (
    AuthCallbackResponse,
    DevLoginRequest,
    IntegrationWhoamiResponse,
    PasswordLoginRequest,
    UserProfileUpdate,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.rbac_service import user_permissions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()
settings = get_settings()


def _user_response(user: User, db: Session | None = None) -> UserResponse:
    org = getattr(user, "organization", None)
    permissions: list[str] = []
    if db is not None:
        permissions = sorted(user_permissions(db, user))
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        department=user.department,
        org_id=getattr(user, "org_id", None),
        role=getattr(user, "role", "USER") or "USER",
        status=getattr(user, "status", "ACTIVE") or "ACTIVE",
        org_name=org.org_name if org else None,
        org_type=org.org_type if org else None,
        client_name=org.client_name if org else None,
        permissions=permissions,
    )


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

    try:
        result = auth_service.dev_login(db, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return AuthCallbackResponse(
        access_token=result["access_token"],
        user=_user_response(result["user"], db),
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
        user=_user_response(result["user"], db),
    )


@router.get("/me")
def get_me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
) -> UserResponse | IntegrationWhoamiResponse:
    """User profile (JWT) or SmartOps whoami (PAT).

    SmartOps Test connection must send ``Authorization: Bearer <pat_…>``.
    A valid PAT returns 200 with organization_id / token_status.
    Invalid or revoked PAT → 401.
    """
    raw = get_raw_bearer(credentials)
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = try_pat_principal(db, raw)
    if principal:
        return whoami_response(principal)

    user = auth_service.get_current_user(db, raw)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _user_response(user, db)


@router.put("/me", response_model=UserResponse)
def update_me(
    data: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the signed-in user's profile."""
    try:
        user = auth_service.update_profile(db, current_user, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _user_response(user, db)


@router.post("/logout")
def logout():
    """Logout endpoint (client-side token removal)."""
    return {"message": "Logged out successfully", "success": True}
