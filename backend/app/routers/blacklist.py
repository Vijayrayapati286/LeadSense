"""Blacklist/suppression list routes.

Entries are only ever added automatically (via excel import cross-check or
event_service on a bounce/complaint) — there is no manual "add" endpoint.
The one write path is the admin override below, which un-suppresses an
address without deleting its history (see SuppressionService.override)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import SuppressionEntryListResponse, SuppressionEntryResponse
from app.services.suppression_service import SuppressionService

router = APIRouter(prefix="/blacklist", tags=["Blacklist"])
suppression_service = SuppressionService()


@router.get("", response_model=SuppressionEntryListResponse)
def list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = suppression_service.list(db, page=page, page_size=page_size, search=search)

    responses = []
    for entry in items:
        response = SuppressionEntryResponse.model_validate(entry)
        response.campaign_name = entry.campaign.campaign_name if entry.campaign else None
        responses.append(response)

    return SuppressionEntryListResponse(
        items=responses, total=total, page=page, page_size=page_size
    )


@router.post("/{entry_id}/override", response_model=SuppressionEntryResponse)
def override_suppression(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin override: allow this address to receive campaigns/follow-ups
    again. The suppression entry is kept as a historical record — only its
    `overridden_at` timestamp is set."""
    try:
        entry = suppression_service.override(db, entry_id)
        response = SuppressionEntryResponse.model_validate(entry)
        response.campaign_name = entry.campaign.campaign_name if entry.campaign else None
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
