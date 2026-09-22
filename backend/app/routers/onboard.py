"""Public email verification + invite acceptance (no login required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Organization, User
from app.routers.auth import _user_response
from app.schemas.schemas import UserResponse
from app.services import onboard_service

router = APIRouter(prefix="/onboard", tags=["Onboarding"])


class VerifyPreviewResponse(BaseModel):
    email: str
    name: str
    org_name: str | None = None
    client_name: str | None = None
    kind: str


class CompletePasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)
    name: str | None = Field(None, min_length=1, max_length=255)


class CompleteAuthResponse(BaseModel):
    message: str
    user: UserResponse


def _org_for_user(db: Session, user: User) -> Organization | None:
    if not user.org_id:
        return None
    return db.query(Organization).filter(Organization.org_id == user.org_id).first()


@router.get("/verify/{token}", response_model=VerifyPreviewResponse)
def preview_owner_verify(token: str, db: Session = Depends(get_db)):
    try:
        row = onboard_service.get_owner_verification(db, token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    org = _org_for_user(db, user)
    return VerifyPreviewResponse(
        email=user.email,
        name=user.name,
        org_name=org.org_name if org else None,
        client_name=org.client_name if org else None,
        kind="owner",
    )


@router.post("/verify/{token}", response_model=CompleteAuthResponse)
def complete_owner_verify(
    token: str,
    data: CompletePasswordRequest,
    db: Session = Depends(get_db),
):
    try:
        user = onboard_service.complete_owner_verification(
            db, token, password=data.password, name=data.name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompleteAuthResponse(message="Email verified. You can sign in now.", user=_user_response(user, db))


@router.get("/invite/{token}", response_model=VerifyPreviewResponse)
def preview_invite(token: str, db: Session = Depends(get_db)):
    try:
        invite = onboard_service.get_pending_invite(db, token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    org = db.query(Organization).filter(Organization.org_id == invite.org_id).first()
    return VerifyPreviewResponse(
        email=invite.email,
        name=invite.email.split("@")[0],
        org_name=org.org_name if org else None,
        client_name=org.client_name if org else None,
        kind="invite",
    )


@router.post("/invite/{token}", response_model=CompleteAuthResponse)
def complete_invite(
    token: str,
    data: CompletePasswordRequest,
    db: Session = Depends(get_db),
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    try:
        _invite, user = onboard_service.complete_invite(
            db, token, name=name, password=data.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompleteAuthResponse(message="Invite accepted. You can sign in now.", user=_user_response(user, db))
