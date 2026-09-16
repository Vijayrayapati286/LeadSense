"""Tenant invite routes — ADMIN only, scoped to authenticated org_id."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import Literal

from app.database.connection import get_db
from app.middleware.tenant import require_admin_user, require_org_id
from app.models import Invite, User
from app.schemas.schemas import MessageResponse, UserResponse
from app.routers.auth import _user_response
from app.services import invite_service

router = APIRouter(prefix="/invites", tags=["Invites"])


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["ADMIN", "USER"] = "USER"


class InviteAcceptRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class InviteResponse(BaseModel):
    id: int
    org_id: str
    email: str
    role: str
    status: str
    invited_by: str | None = None
    invited_by_user_id: int | None = None
    expires_at: str | None = None
    resolved_at: str | None = None
    resolved_note: str | None = None
    created_at: str | None = None


class InviteAcceptResponse(BaseModel):
    invite: InviteResponse
    user: UserResponse


def _get_org_invite(db: Session, invite_id: int, org_id: str) -> Invite:
    invite = db.query(Invite).filter(Invite.id == invite_id, Invite.org_id == org_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    return invite


@router.get("", response_model=list[InviteResponse])
def list_invites(
    status: str | None = Query(None),
    search: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org_id = require_org_id(current_user)
    rows = invite_service.list_invites(db, org_id, status=status, search=search)
    return [InviteResponse(**invite_service.invite_to_dict(r)) for r in rows]


@router.post("", response_model=InviteResponse, status_code=201)
def create_invite(
    data: InviteCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org_id = require_org_id(current_user)
    try:
        invite = invite_service.create_invite(
            db, org_id=org_id, email=str(data.email), role=data.role, invited_by=current_user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return InviteResponse(**invite_service.invite_to_dict(invite))


@router.post("/{invite_id}/cancel", response_model=InviteResponse)
def cancel_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org_id = require_org_id(current_user)
    invite = _get_org_invite(db, invite_id, org_id)
    try:
        invite = invite_service.cancel_invite(db, invite, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return InviteResponse(**invite_service.invite_to_dict(invite))


@router.post("/{invite_id}/accept", response_model=InviteAcceptResponse)
def accept_invite(
    invite_id: int,
    data: InviteAcceptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Admin completes an invite by creating the member account."""
    org_id = require_org_id(current_user)
    invite = _get_org_invite(db, invite_id, org_id)
    try:
        invite, user = invite_service.accept_invite(
            db, invite, name=data.name, password=data.password, actor=current_user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return InviteAcceptResponse(
        invite=InviteResponse(**invite_service.invite_to_dict(invite)),
        user=_user_response(user),
    )


@router.delete("/{invite_id}", response_model=MessageResponse)
def delete_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    org_id = require_org_id(current_user)
    invite = _get_org_invite(db, invite_id, org_id)
    db.delete(invite)
    db.commit()
    return MessageResponse(message="Invite deleted")
