"""Reusable Mailer library routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import MailerCreate, MailerResponse, MailerUpdate, MessageResponse
from app.services.mailer_service import MailerService

router = APIRouter(prefix="/mailers", tags=["Mailers"])
mailer_service = MailerService()


@router.post("", response_model=MailerResponse, status_code=201)
def create_mailer(
    data: MailerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mailer = mailer_service.create(db, data.model_dump())
    return MailerResponse.model_validate(mailer)


@router.get("", response_model=list[MailerResponse])
def list_mailers(
    search: str = Query("", alias="search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mailers = mailer_service.list_mailers(db, search=search)
    return [MailerResponse.model_validate(m) for m in mailers]


@router.get("/{mailer_id}", response_model=MailerResponse)
def get_mailer(
    mailer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mailer = mailer_service.get_by_id(db, mailer_id)
    if not mailer:
        raise HTTPException(status_code=404, detail="Mailer not found")
    return MailerResponse.model_validate(mailer)


@router.put("/{mailer_id}", response_model=MailerResponse)
def update_mailer(
    mailer_id: int,
    data: MailerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        mailer = mailer_service.update(db, mailer_id, data.model_dump(exclude_unset=True))
        return MailerResponse.model_validate(mailer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{mailer_id}", response_model=MessageResponse)
def delete_mailer(
    mailer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        mailer_service.delete(db, mailer_id)
        return MessageResponse(message="Mailer deleted")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
