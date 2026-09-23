"""SmartOps lead / work-item APIs — scoped by PAT organization_id."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.pat_auth import require_org_scope, security as bearer_security
from app.schemas.schemas import LeadCreateRequest, LeadListResponse, LeadResponse, LeadUpdateRequest
from app.services import lead_service

router = APIRouter(prefix="/leads", tags=["Leads"])
org_leads_router = APIRouter(prefix="/organizations", tags=["Leads"])


def _as_response(row) -> LeadResponse:
    return LeadResponse.model_validate(row)


@router.get("", response_model=LeadListResponse)
def list_leads(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    org_id, _, _ = require_org_scope(credentials, db)
    items, total = lead_service.list_leads(
        db, org_id, status=status_filter, page=page, page_size=page_size
    )
    return LeadListResponse(
        items=[_as_response(row) for row in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    data: LeadCreateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    org_id, _, _ = require_org_scope(credentials, db)
    try:
        row = lead_service.create_lead(db, org_id, data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _as_response(row)


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    org_id, _, _ = require_org_scope(credentials, db)
    row = lead_service.get_lead(db, org_id, lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _as_response(row)


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: str,
    data: LeadUpdateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    org_id, _, _ = require_org_scope(credentials, db)
    row = lead_service.get_lead(db, org_id, lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        row = lead_service.update_lead(db, row, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _as_response(row)


@org_leads_router.get("/{organization_id}/leads", response_model=LeadListResponse)
def list_org_leads(
    organization_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    org_id, _, _ = require_org_scope(credentials, db, path_org_id=organization_id)
    items, total = lead_service.list_leads(
        db, org_id, status=status_filter, page=page, page_size=page_size
    )
    return LeadListResponse(
        items=[_as_response(row) for row in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@org_leads_router.post(
    "/{organization_id}/leads",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_org_lead(
    organization_id: str,
    data: LeadCreateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    db: Session = Depends(get_db),
):
    org_id, _, _ = require_org_scope(credentials, db, path_org_id=organization_id)
    try:
        row = lead_service.create_lead(db, org_id, data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _as_response(row)
