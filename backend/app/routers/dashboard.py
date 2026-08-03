"""Dashboard routes."""

import io
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
dashboard_service = DashboardService()


def _date_range_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Turn inclusive calendar-day query params into UTC datetime bounds —
    date_to covers through the end of that day, not just midnight."""
    dt_from = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    dt_to = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return dt_from, dt_to


@router.get("/stats", response_model=DashboardResponse)
def get_dashboard_stats(
    user_id: int | None = Query(None),
    campaign_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated dashboard statistics and charts data, optionally
    narrowed by sender/owner, campaign, and/or a date range."""
    dt_from, dt_to = _date_range_bounds(date_from, date_to)
    data = dashboard_service.get_full_dashboard(db, user_id, campaign_id, dt_from, dt_to)
    return DashboardResponse(**data)


@router.get("/export-report")
def export_report(
    user_id: int | None = Query(None),
    campaign_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Multi-sheet Excel export (summary stats, campaigns, prospects, email
    send history) for the Dashboard's "Export Report" button — respects the
    same filters currently applied on screen."""
    dt_from, dt_to = _date_range_bounds(date_from, date_to)
    content = dashboard_service.build_report_workbook(db, user_id, campaign_id, dt_from, dt_to)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leadsense_report.xlsx"},
    )
