"""Approved custom merge-field names — registered the first time someone
chooses to proceed with a {{Field}} placeholder outside the standard header
set, so templates using it aren't flagged again."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import CustomField, User
from app.schemas.schemas import CustomFieldCreate, CustomFieldResponse

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])


@router.get("", response_model=list[CustomFieldResponse])
def list_custom_fields(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(CustomField).order_by(CustomField.name).all()


@router.post("", response_model=CustomFieldResponse, status_code=201)
def create_custom_field(
    data: CustomFieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = data.name.strip()
    existing = db.query(CustomField).filter(CustomField.name == name).first()
    if existing:
        return existing
    field = CustomField(name=name)
    db.add(field)
    db.commit()
    db.refresh(field)
    return field
