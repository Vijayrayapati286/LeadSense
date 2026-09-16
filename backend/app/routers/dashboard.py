"""Dashboard routes."""

import io
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.middleware.tenant import require_admin_user, require_org_id
from app.models import User
from app.schemas.schemas import AdminDashboardResponse, DashboardResponse
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.dashboard_service import DashboardService
from app.services.tenant_constants import ROLE_ADMIN

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
dashboard_service = DashboardService()
admin_dashboard_service = AdminDashboardService()


def _date_range_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Turn inclusive calendar-day query params into UTC datetime bounds —
    date_to covers through the end of that day, not just midnight."""
    dt_from = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    dt_to = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return dt_from, dt_to


def _resolve_scoped_user_id(current_user: User, requested_user_id: int | None) -> int | None:
    """Never trust a cross-tenant user_id from the client."""
    org_id = getattr(current_user, "org_id", None)
    role = getattr(current_user, "role", None)

    if role != ROLE_ADMIN:
        return current_user.id

    if requested_user_id is None:
        return None

    # ADMIN may filter by user only within their own org
    if org_id:
        # Verified in the route against DB; here we just pass through and
        # validate below when db is available.
        return requested_user_id
    return current_user.id


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
    org_id = getattr(current_user, "org_id", None)
    role = getattr(current_user, "role", None)

    scoped_user_id = user_id
    if role != ROLE_ADMIN:
        scoped_user_id = current_user.id
    elif user_id is not None and org_id:
        target = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        scoped_user_id = user_id

    if campaign_id is not None and org_id:
        from app.models import Campaign

        camp = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.org_id == org_id).first()
        if not camp:
            raise HTTPException(status_code=404, detail="Campaign not found")

    dt_from, dt_to = _date_range_bounds(date_from, date_to)
    data = dashboard_service.get_full_dashboard(
        db, scoped_user_id, campaign_id, dt_from, dt_to, org_id=org_id
    )
    return DashboardResponse(**data)


@router.get("/admin", response_model=AdminDashboardResponse)
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Tenant-wide admin dashboard — scoped strictly to the admin's org_id."""
    org_id = require_org_id(current_user)
    data = admin_dashboard_service.get_admin_dashboard(db, org_id)
    return AdminDashboardResponse(**data)


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
    org_id = getattr(current_user, "org_id", None)
    role = getattr(current_user, "role", None)

    scoped_user_id = user_id
    if role != ROLE_ADMIN:
        scoped_user_id = current_user.id
    elif user_id is not None and org_id:
        target = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

    dt_from, dt_to = _date_range_bounds(date_from, date_to)
    content = dashboard_service.build_report_workbook(
        db, scoped_user_id, campaign_id, dt_from, dt_to, org_id=org_id
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leadsense_report.xlsx"},
    )
