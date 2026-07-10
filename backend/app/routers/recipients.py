"""Recipient management routes."""

import csv
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Recipient, SavedSearch, User
from app.schemas.schemas import (
    MessageResponse,
    RecipientListResponse,
    RecipientResponse,
    SavedSearchCreate,
    SavedSearchResponse,
    SelectRecipientsRequest,
    UploadExcelResponse,
)
from app.services.excel_service import ExcelService
from app.services.recipient_group_service import RecipientGroupService
from app.services.recipient_query_service import (
    DISTINCT_VALUE_FIELDS,
    RecipientSearchFilters,
    build_query,
    get_distinct_values,
)

router = APIRouter(prefix="/recipients", tags=["Recipients"])
excel_service = ExcelService()
group_service = RecipientGroupService()

EXPORT_COLUMNS = [
    "id", "name", "email", "company", "designation", "designation_level", "industry",
    "department", "country", "state", "city", "company_size",
    "years_of_experience", "skills", "status", "source",
]


def _search_filters(
    search: str = Query("", alias="search"),
    name: str = Query(""),
    email: str = Query(""),
    designation: list[str] = Query([]),
    company: str = Query(""),
    industry: list[str] = Query([]),
    department: str = Query(""),
    country: list[str] = Query([]),
    state: list[str] = Query([]),
    city: list[str] = Query([]),
    company_size: str = Query(""),
    years_of_experience: str = Query(""),
    skills: list[str] = Query([]),
    seniority_level: list[str] = Query([]),
    email_domain: str = Query(""),
    lead_status: list[str] = Query([]),
    source: str = Query(""),
    group_ids: list[int] = Query([]),
    tag_ids: list[int] = Query([]),
    campaign_id: int | None = Query(None),
    campaign_status: str = Query(""),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
) -> RecipientSearchFilters:
    return RecipientSearchFilters(
        search=search, name=name, email=email, designation=designation, company=company, industry=industry,
        department=department, country=country, state=state, city=city,
        company_size=company_size, years_of_experience=years_of_experience, skills=skills,
        seniority_level=seniority_level, email_domain=email_domain, lead_status=lead_status,
        source=source, group_ids=group_ids, tag_ids=tag_ids,
        campaign_id=campaign_id, campaign_status=campaign_status,
        sort_by=sort_by, sort_order=sort_order,
    )


@router.post("/upload-excel", response_model=UploadExcelResponse)
async def upload_excel(
    file: UploadFile = File(...),
    group_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported")

    content = await file.read()
    try:
        imported, recipient_ids = excel_service.import_recipients(db, content)

        if group_name:
            group = group_service.get_or_create(db, group_name)
            group_service.add_members(db, group.id, recipient_ids)

        message = f"Successfully imported {imported} recipients"
        if group_name:
            message += f" into group '{group_name}'"

        return UploadExcelResponse(imported=imported, message=message, group_name=group_name)
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


@router.get("/search", response_model=RecipientListResponse)
def search_recipients(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    filters: RecipientSearchFilters = Depends(_search_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Advanced multi-field prospect search — combines every filter with AND."""
    query = build_query(db, filters)
    total = query.count()
    selected_count = db.query(Recipient).filter(Recipient.is_selected == True).count()

    recipients = query.offset((page - 1) * page_size).limit(page_size).all()

    return RecipientListResponse(
        items=[RecipientResponse.model_validate(r) for r in recipients],
        total=total,
        page=page,
        page_size=page_size,
        selected_count=selected_count,
    )


@router.get("/distinct-values")
def distinct_values(
    field: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real values currently in the database for a given field — used to
    populate multi-select dropdown options (Industry, Designation, Skills,
    Location, etc.) instead of a hardcoded list."""
    if field not in DISTINCT_VALUE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported field '{field}'")
    return {"field": field, "values": get_distinct_values(db, field)}


@router.get("/search-ids")
def search_recipient_ids(
    filters: RecipientSearchFilters = Depends(_search_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All recipient ids matching the current filters (not just one page) —
    powers "select all matching results" for bulk group/campaign actions."""
    query = build_query(db, filters)
    ids = [r.id for r in query.all()]
    return {"ids": ids, "total": len(ids)}


@router.get("/export")
def export_recipients(
    filters: RecipientSearchFilters = Depends(_search_filters),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export every recipient matching the current search filters as CSV
    (not just the current page)."""
    query = build_query(db, filters)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for r in query.all():
        writer.writerow([getattr(r, col) or "" for col in EXPORT_COLUMNS])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=prospects_export.csv"},
    )


@router.post("/saved-searches", response_model=SavedSearchResponse, status_code=201)
def create_saved_search(
    data: SavedSearchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = SavedSearch(user_id=current_user.id, name=data.name, filters=json.dumps(data.filters))
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return SavedSearchResponse(
        id=saved.id, name=saved.name, filters=data.filters, created_at=saved.created_at
    )


@router.get("/saved-searches", response_model=list[SavedSearchResponse])
def list_saved_searches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved_searches = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == current_user.id)
        .order_by(SavedSearch.created_at.desc())
        .all()
    )
    return [
        SavedSearchResponse(
            id=s.id, name=s.name, filters=json.loads(s.filters), created_at=s.created_at
        )
        for s in saved_searches
    ]


@router.delete("/saved-searches/{saved_search_id}", response_model=MessageResponse)
def delete_saved_search(
    saved_search_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = (
        db.query(SavedSearch)
        .filter(SavedSearch.id == saved_search_id, SavedSearch.user_id == current_user.id)
        .first()
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")
    db.delete(saved)
    db.commit()
    return MessageResponse(message="Saved search deleted")


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
