"""Dashboard routes."""

from fastapi import APIRouter, Depends
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
