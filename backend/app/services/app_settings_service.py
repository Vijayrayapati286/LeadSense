"""Runtime-configurable deliverability settings (single-row table)."""

import json

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

settings = get_settings()


class AppSettingsService:
    def get(self, db: Session) -> AppSetting:
        row = db.query(AppSetting).filter(AppSetting.id == 1).first()
        if not row:
            row = AppSetting(
                id=1,
                soft_bounce_threshold=settings.soft_bounce_threshold,
                send_interval_seconds=12,
                suppress_on_tags="[]",
                business_hours_start=9,
                business_hours_end=18,
                default_page_size=10,
                default_ai_tone="formal",
                default_use_recipient_timezone=False,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    def get_suppress_on_tags(self, db: Session) -> list[str]:
        return json.loads(self.get(db).suppress_on_tags or "[]")

    def update(self, db: Session, update_data: dict) -> AppSetting:
        row = self.get(db)
        if "suppress_on_tags" in update_data and update_data["suppress_on_tags"] is not None:
            update_data["suppress_on_tags"] = json.dumps(update_data["suppress_on_tags"])
        for field, value in update_data.items():
            if value is not None:
                setattr(row, field, value)
        db.commit()
        db.refresh(row)
        return row
