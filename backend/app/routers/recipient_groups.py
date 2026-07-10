"""Recipient group (team/list) management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import (
    AddGroupMembersRequest,
    MessageResponse,
    RecipientGroupCreate,
    RecipientGroupResponse,
    RecipientGroupUpdate,
    RecipientListResponse,
    RecipientResponse,
)
from app.services.recipient_group_service import RecipientGroupService

router = APIRouter(prefix="/recipient-groups", tags=["Recipient Groups"])
group_service = RecipientGroupService()


def _to_response(group, prospect_count: int) -> RecipientGroupResponse:
    response = RecipientGroupResponse.model_validate(group)
    response.prospect_count = prospect_count
    return response


@router.post("", response_model=RecipientGroupResponse, status_code=201)
def create_group(
    data: RecipientGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        group = group_service.create(db, data.name, data.description)
        return _to_response(group, 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[RecipientGroupResponse])
def list_groups(
    search: str = Query("", alias="search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = group_service.list_groups(db, search=search)
    return [_to_response(r["group"], r["prospect_count"]) for r in results]


@router.get("/{group_id}", response_model=RecipientGroupResponse)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = group_service.get_by_id(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _, total = group_service.get_members(db, group_id, page=1, page_size=1)
    return _to_response(group, total)


@router.put("/{group_id}", response_model=RecipientGroupResponse)
def update_group(
    group_id: int,
    data: RecipientGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        group = group_service.rename(db, group_id, data.name, data.description)
        _, total = group_service.get_members(db, group_id, page=1, page_size=1)
        return _to_response(group, total)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{group_id}", response_model=MessageResponse)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        group_service.delete(db, group_id)
        return MessageResponse(message="Group deleted successfully")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{group_id}/members", response_model=RecipientListResponse)
def get_group_members(
    group_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not group_service.get_by_id(db, group_id):
        raise HTTPException(status_code=404, detail="Group not found")

    items, total = group_service.get_members(db, group_id, page=page, page_size=page_size, search=search)
    return RecipientListResponse(
        items=[RecipientResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        selected_count=0,
    )


@router.post("/{group_id}/members", response_model=MessageResponse)
def add_group_members(
    group_id: int,
    data: AddGroupMembersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        added = group_service.add_members(db, group_id, data.recipient_ids)
        return MessageResponse(message=f"Added {added} recipient(s) to group")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{group_id}/members/{recipient_id}", response_model=MessageResponse)
def remove_group_member(
    group_id: int,
    recipient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group_service.remove_member(db, group_id, recipient_id)
    return MessageResponse(message="Removed recipient from group")
