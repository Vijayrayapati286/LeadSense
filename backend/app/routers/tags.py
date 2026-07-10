"""Tag management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import AssignTagRequest, MessageResponse, TagCreate, TagResponse
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["Tags"])
tag_service = TagService()


def _to_response(tag, recipient_count: int) -> TagResponse:
    response = TagResponse.model_validate(tag)
    response.recipient_count = recipient_count
    return response


@router.post("", response_model=TagResponse, status_code=201)
def create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = tag_service.get_or_create(db, data.name)
    return _to_response(tag, 0)


@router.get("", response_model=list[TagResponse])
def list_tags(
    search: str = Query("", alias="search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = tag_service.list_tags(db, search=search)
    return [_to_response(r["tag"], r["recipient_count"]) for r in results]


@router.delete("/{tag_id}", response_model=MessageResponse)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        tag_service.delete(db, tag_id)
        return MessageResponse(message="Tag deleted")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{tag_id}/members", response_model=MessageResponse)
def assign_tag(
    tag_id: int,
    data: AssignTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        added = tag_service.assign(db, tag_id, data.recipient_ids)
        return MessageResponse(message=f"Tagged {added} recipient(s)")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{tag_id}/members/{recipient_id}", response_model=MessageResponse)
def unassign_tag(
    tag_id: int,
    recipient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag_service.unassign(db, tag_id, recipient_id)
    return MessageResponse(message="Tag removed from recipient")
