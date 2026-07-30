"""Dashboard routes."""

import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
dashboard_service = DashboardService()


@router.get("/stats", response_model=DashboardResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated dashboard statistics and charts data."""
    data = dashboard_service.get_full_dashboard(db)
    return DashboardResponse(**data)


@router.get("/export-report")
def export_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Multi-sheet Excel export (summary stats, campaigns, prospects, email
    send history) for the Dashboard's "Export Report" button."""
    content = dashboard_service.build_report_workbook(db)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leadsense_report.xlsx"},
    )
