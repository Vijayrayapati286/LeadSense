"""Organization + PAT management for SmartOps integration handoff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.pat_auth import get_raw_bearer, require_org_scope, security as bearer_security, try_pat_principal
from app.middleware.tenant import is_provider_admin, require_admin_user, require_provider_admin
from app.models import Organization, OrganizationToken, User
from app.services.auth_service import AuthService
from app.services import onboard_service
from app.services.tenant_constants import ROLE_ADMIN, STATUS_ACTIVE
from app.schemas.schemas import (
    OrganizationCreateRequest,
    OrganizationCreateResponse,
    OrganizationResponse,
    OrganizationTokenCreateRequest,
    OrganizationTokenCreateResponse,
    OrganizationTokenResponse,
)
from app.services import organization_token_service as pat_service

router = APIRouter(prefix="/organizations", tags=["Organizations"])
_auth_service = AuthService()


def _require_admin_from_jwt(db: Session, raw: str) -> User:
    user = _auth_service.get_current_user(db, raw)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if getattr(user, "role", None) != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if getattr(user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")
    if not getattr(user, "org_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to a tenant organization",
        )
    return user


def _org_response(org: Organization) -> OrganizationResponse:
    return OrganizationResponse(
        organization_id=org.org_id,
        name=org.org_name,
        type=org.org_type,
        status=org.status,
        client_name=org.client_name,
        owner_user_id=org.owner_user_id,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def _token_response(token: OrganizationToken) -> OrganizationTokenResponse:
    return OrganizationTokenResponse(
        token_id=token.token_id,
        organization_id=token.organization_id,
        token_prefix=token.token_prefix,
        name=token.name,
        scopes=pat_service.scopes_from_json(token.scopes),
        status=token.status,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        expires_at=token.expires_at,
    )


def _token_create_response(token: OrganizationToken, raw: str) -> OrganizationTokenCreateResponse:
    base = _token_response(token)
    return OrganizationTokenCreateResponse(**base.model_dump(), token=raw)


def _require_manageable_org(db: Session, org_id: str, user: User) -> Organization:
    org = db.query(Organization).filter(Organization.org_id == org_id).first()
    if not org or not pat_service.can_manage_org(user, org):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/me", response_model=OrganizationResponse)
def get_my_organization(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    """Return the PAT-bound org, or the signed-in admin's organization."""
    org_id, _principal, _user = require_org_scope(credentials, db)
    org = db.query(Organization).filter(Organization.org_id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _org_response(org)


@router.get("", response_model=list[OrganizationResponse])
def list_manageable_organizations(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    """PAT: the bound org only. JWT admin: orgs they belong to or created."""
    raw = get_raw_bearer(credentials)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = try_pat_principal(db, raw)
    if principal:
        return [_org_response(principal.organization)]

    current_user = _require_admin_from_jwt(db, raw)
    query = db.query(Organization)
    if is_provider_admin(current_user):
        orgs = query.order_by(Organization.org_name).all()
    else:
        orgs = (
            query.filter(Organization.org_id == current_user.org_id)
            .order_by(Organization.org_name)
            .all()
        )
    seen: set[str] = set()
    out: list[OrganizationResponse] = []
    for org in orgs:
        if org.org_id in seen:
            continue
        seen.add(org.org_id)
        out.append(_org_response(org))
    return out


@router.post("", response_model=OrganizationCreateResponse, status_code=201)
def create_organization(
    data: OrganizationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_provider_admin),
):
    """Provider admin onboards a TENANT org, emails that org's admin, and mints a PAT."""
    try:
        org, token_row, raw, owner, verify_url = onboard_service.onboard_tenant(
            db,
            org_name=data.name,
            client_name=data.client_name or data.owner_name,
            owner_name=data.owner_name,
            owner_email=str(data.owner_email),
            created_by=current_user,
            pat_name=data.pat_name or "SmartOps",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not token_row or not raw:
        raise HTTPException(status_code=500, detail="Organization created but PAT mint failed")

    return OrganizationCreateResponse(
        **_org_response(org).model_dump(),
        token=_token_create_response(token_row, raw),
        owner_email=owner.email,
        owner_verify_url=verify_url,
    )


@router.get("/{org_id}/tokens", response_model=list[OrganizationTokenResponse])
def list_organization_tokens(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    _require_manageable_org(db, org_id, current_user)
    return [_token_response(t) for t in pat_service.list_pats(db, org_id)]


@router.post(
    "/{org_id}/tokens",
    response_model=OrganizationTokenCreateResponse,
    status_code=201,
)
def create_organization_token(
    org_id: str,
    data: OrganizationTokenCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org = _require_manageable_org(db, org_id, current_user)
    try:
        token_row, raw = pat_service.create_pat(
            db,
            org=org,
            name=data.name,
            scopes=data.scopes,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _token_create_response(token_row, raw)


@router.post("/{org_id}/tokens/{token_id}/revoke", response_model=OrganizationTokenResponse)
def revoke_organization_token(
    org_id: str,
    token_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    _require_manageable_org(db, org_id, current_user)
    token = (
        db.query(OrganizationToken)
        .filter(
            OrganizationToken.token_id == token_id,
            OrganizationToken.organization_id == org_id,
        )
        .first()
    )
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return _token_response(pat_service.revoke_pat(db, token))


@router.get("/{org_id}", response_model=OrganizationResponse)
def get_organization(
    org_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    """200 only when the PAT belongs to this org, or a JWT admin can manage it."""
    raw = get_raw_bearer(credentials)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = try_pat_principal(db, raw)
    if principal:
        if principal.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Organization not found")
        return _org_response(principal.organization)

    current_user = _require_admin_from_jwt(db, raw)
    org = _require_manageable_org(db, org_id, current_user)
    return _org_response(org)
