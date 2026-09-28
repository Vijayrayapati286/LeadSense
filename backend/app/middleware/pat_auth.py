"""PAT (integration) authentication dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Organization, OrganizationToken, User
from app.schemas.schemas import IntegrationWhoamiResponse
from app.services import organization_token_service as pat_service
from app.services.auth_service import AuthService

security = HTTPBearer(auto_error=False)
_auth_service = AuthService()

_AUTH_HEADERS = {"WWW-Authenticate": "Bearer"}


@dataclass
class PatPrincipal:
    """Authenticated integration principal (SmartOps / machine client)."""

    token: OrganizationToken
    organization: Organization

    @property
    def organization_id(self) -> str:
        return self.organization.org_id


def get_raw_bearer(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if not credentials or not credentials.credentials:
        return None
    raw = credentials.credentials.strip()
    return raw or None


def try_pat_principal(db: Session, raw_token: str | None) -> PatPrincipal | None:
    if not raw_token:
        return None
    resolved = pat_service.resolve_active_pat(db, raw_token)
    if not resolved:
        return None
    token, org = resolved
    return PatPrincipal(token=token, organization=org)


def whoami_response(principal: PatPrincipal) -> IntegrationWhoamiResponse:
    org = principal.organization
    token = principal.token
    return IntegrationWhoamiResponse(
        organization_id=org.org_id,
        organization_name=org.org_name,
        type=org.org_type,
        token_status=token.status.lower() if token.status else "active",
        token_id=None if token.token_id == "tok_legacy" else token.token_id,
        token_name=token.name,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_AUTH_HEADERS,
    )


def require_org_scope(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    *,
    path_org_id: str | None = None,
) -> tuple[str, PatPrincipal | None, User | None]:
    """Resolve PAT first (SmartOps), then LeadSense JWT. Returns (organization_id, pat, user)."""
    raw = get_raw_bearer(credentials)
    if not raw:
        raise _unauthorized("Not authenticated")

    principal = try_pat_principal(db, raw)
    if principal:
        org_id = principal.organization_id
        if path_org_id and path_org_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        return org_id, principal, None

    user = _auth_service.get_current_user(db, raw)
    if not user:
        raise _unauthorized("Invalid or expired token")
    org_id = getattr(user, "org_id", None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to a tenant organization",
        )
    if path_org_id and path_org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org_id, None, user


async def get_pat_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> PatPrincipal:
    raw = get_raw_bearer(credentials)
    if not raw:
        raise _unauthorized("Not authenticated")
    principal = try_pat_principal(db, raw)
    if not principal:
        raise _unauthorized("Invalid or revoked token")
    return principal
