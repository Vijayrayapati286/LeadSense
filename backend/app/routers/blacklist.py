"""Read-only blacklist/suppression list routes. There is deliberately no
create/update/delete endpoint here — entries are only ever added by
suppression_service (via excel import cross-check or event_service), never
edited or removed through the API."""

from fastapi import APIRouter, Depends, Query
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
