"""ICP Database REST API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.icp.schemas import (
    IcpAccountListResponse,
    IcpListResponse,
    IcpRecordCreate,
    IcpRecordResponse,
    IcpRecordUpdate,
)
from app.icp.service import (
    count_icp_records,
    create_icp_record,
    delete_icp_record,
    get_icp_record,
    list_accounts_summary,
    list_icp_records,
    serialize_icp,
    update_icp_record,
    upsert_icp_from_bulk_item,
)
from app.linkedin.bulk_jobs import get_job_row
from app.linkedin.bulk_models import BulkJobItemRow
from app.middleware.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/icp", tags=["ICP Database"])


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(f"{text}T00:00:00+00:00")
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date: {value}") from exc


@router.get("", response_model=IcpListResponse)
def list_icp(
    search: str = Query(""),
    industry: str = Query(""),
    company: str = Query(""),
    company_name: str = Query(""),
    company_size: str = Query(""),
    designation: str = Query(""),
    location: str = Query(""),
    icp_status: str = Query(""),
    created_from: str = Query(""),
    created_to: str = Query(""),
    verified_from: str = Query(""),
    verified_to: str = Query(""),
    sort_by: str = Query("verified_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    size = page_size or limit
    result = list_icp_records(
        db,
        user_id=getattr(current_user, "id", None),
        search=search or None,
        industry=industry or None,
        company=company or company_name or None,
        company_size=company_size or None,
        designation=designation or None,
        location=location or None,
        icp_status=icp_status or None,
        created_from=_parse_date(created_from or None),
        created_to=_parse_date(created_to or None),
        verified_from=_parse_date(verified_from or None),
        verified_to=_parse_date(verified_to or None),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=size,
    )
    return result


@router.get("/accounts", response_model=IcpAccountListResponse)
def list_accounts(
    search: str = Query(""),
    industry: str = Query(""),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=500),
    page_size: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    size = page_size or limit
    return list_accounts_summary(
        db,
        user_id=getattr(current_user, "id", None),
        search=search or None,
        industry=industry or None,
        page=page,
        page_size=size,
    )


@router.get("/count")
def icp_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"total": count_icp_records(db, user_id=getattr(current_user, "id", None))}


@router.get("/{record_id}", response_model=IcpRecordResponse)
def get_icp(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_icp_record(db, record_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP record not found")
    return serialize_icp(row)


@router.post("", response_model=IcpRecordResponse, status_code=201)
def create_icp(
    body: IcpRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = create_icp_record(db, user_id=getattr(current_user, "id", None), data=body.model_dump())
    db.commit()
    db.refresh(row)
    return serialize_icp(row)


@router.put("/{record_id}", response_model=IcpRecordResponse)
def update_icp(
    record_id: int,
    body: IcpRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_icp_record(db, record_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP record not found")
    update_icp_record(db, row, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return serialize_icp(row)


@router.delete("/{record_id}")
def delete_icp(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_icp_record(db, record_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP record not found")
    delete_icp_record(db, row)
    db.commit()
    return {"ok": True, "id": record_id}


@router.post("/sync/bulk-item/{item_id}")
def sync_from_bulk_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retry ICP sync for a verified/resolved bulk job item."""
    user_id = getattr(current_user, "id", None)
    item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bulk item not found")
    job = get_job_row(db, item.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if user_id is not None and job.user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        row = upsert_icp_from_bulk_item(db, item, user_id=job.user_id or user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return {"icp_synced": True, "icp_record": serialize_icp(row)}
