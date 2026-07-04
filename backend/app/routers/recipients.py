"""Recipient management routes."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Recipient, User
from app.schemas.schemas import (
    MessageResponse,
    RecipientListResponse,
    RecipientResponse,
    SelectRecipientsRequest,
    UploadExcelResponse,
)
from app.services.excel_service import ExcelService

router = APIRouter(prefix="/recipients", tags=["Recipients"])
excel_service = ExcelService()


@router.post("/upload-excel", response_model=UploadExcelResponse)
async def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported")

    content = await file.read()
    try:
        imported = excel_service.import_recipients(db, content)
        return UploadExcelResponse(
            imported=imported,
            message=f"Successfully imported {imported} recipients",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=RecipientListResponse)
def list_recipients(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    industry: str = Query("", alias="industry"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Recipient)

    if search:
        term = f"%{search}%"
        query = query.filter(
            (Recipient.name.ilike(term))
            | (Recipient.email.ilike(term))
            | (Recipient.company.ilike(term))
        )

    if industry:
        query = query.filter(Recipient.industry.ilike(f"%{industry}%"))

    total = query.count()
    selected_count = db.query(Recipient).filter(Recipient.is_selected == True).count()

    recipients = (
        query.order_by(Recipient.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return RecipientListResponse(
        items=[RecipientResponse.model_validate(r) for r in recipients],
        total=total,
        page=page,
        page_size=page_size,
        selected_count=selected_count,
    )


@router.post("/select-recipients", response_model=MessageResponse)
def select_recipients(
    data: SelectRecipientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.deselect_all:
        db.query(Recipient).update({Recipient.is_selected: False})
        db.commit()
        return MessageResponse(message="All recipients deselected")

    if data.select_all:
        db.query(Recipient).update({Recipient.is_selected: True})
        db.commit()
        return MessageResponse(message="All recipients selected")

    if data.recipient_ids:
        # Deselect all first, then select specified
        db.query(Recipient).update({Recipient.is_selected: False})
        db.query(Recipient).filter(Recipient.id.in_(data.recipient_ids)).update(
            {Recipient.is_selected: True}, synchronize_session=False
        )
        db.commit()
        return MessageResponse(message=f"Selected {len(data.recipient_ids)} recipients")

    return MessageResponse(message="No changes made", success=False)
