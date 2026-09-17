"""Organization + PAT management for SmartOps integration handoff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.tenant import require_admin_user
from app.models import Organization, OrganizationToken, User
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


def _org_response(org: Organization) -> OrganizationResponse:
    return OrganizationResponse(
        organization_id=org.org_id,
        name=org.org_name,
        type=org.org_type,
        status=org.status,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Return the signed-in admin's organization (for SmartOps Tenant Id copy)."""
    org = (
        db.query(Organization)
        .filter(Organization.org_id == current_user.org_id)
        .first()
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _org_response(org)


@router.get("", response_model=list[OrganizationResponse])
def list_manageable_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Orgs the admin belongs to or created (ops handoff)."""
    orgs = (
        db.query(Organization)
        .filter(
            or_(
                Organization.org_id == current_user.org_id,
                Organization.created_by_user_id == current_user.id,
            )
        )
        .order_by(Organization.org_name)
        .all()
    )
    # Deduplicate if member + creator of same org
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
    current_user: User = Depends(require_admin_user),
):
    """Create a tenant org and always mint a PAT (shown once for SmartOps)."""
    try:
        org, token_row, raw = pat_service.create_organization(
            db,
            name=data.name,
            org_type=data.type,
            created_by_user_id=current_user.id,
            mint_pat=True,
            pat_name=data.pat_name or "SmartOps",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not token_row or not raw:
        raise HTTPException(status_code=500, detail="Organization created but PAT mint failed")

    return OrganizationCreateResponse(
        **_org_response(org).model_dump(),
        token=_token_create_response(token_row, raw),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org = _require_manageable_org(db, org_id, current_user)
    return _org_response(org)
