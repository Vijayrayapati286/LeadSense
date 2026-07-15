"""Runtime-configurable deliverability settings routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import AppSettingResponse, AppSettingUpdate
from app.services.app_settings_service import AppSettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])
app_settings_service = AppSettingsService()


def _to_response(row) -> AppSettingResponse:
    import json
    return AppSettingResponse(
        soft_bounce_threshold=row.soft_bounce_threshold,
        send_interval_seconds=row.send_interval_seconds,
        suppress_on_tags=json.loads(row.suppress_on_tags or "[]"),
    )


@router.get("/app", response_model=AppSettingResponse)
def get_app_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _to_response(app_settings_service.get(db))


@router.put("/app", response_model=AppSettingResponse)
def update_app_settings(
    data: AppSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = app_settings_service.update(db, data.model_dump(exclude_unset=True))
    return _to_response(row)
