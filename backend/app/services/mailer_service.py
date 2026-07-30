"""Reusable Mailer (named, campaign-independent email template) business logic."""

from sqlalchemy.orm import Session

from app.models import Mailer
from app.utils.helpers import sanitize_html, sanitize_manual_body


class MailerService:
    def create(self, db: Session, data: dict) -> Mailer:
        mailer = Mailer(**sanitize_manual_body(data))
        db.add(mailer)
        db.commit()
        db.refresh(mailer)
        return mailer

    def list_mailers(self, db: Session, search: str = "") -> list[Mailer]:
        query = db.query(Mailer)
        if search:
            query = query.filter(Mailer.name.ilike(f"%{search}%"))
        return query.order_by(Mailer.created_at.desc()).all()

    def get_by_id(self, db: Session, mailer_id: int) -> Mailer | None:
        return db.query(Mailer).filter(Mailer.id == mailer_id).first()

    def update(self, db: Session, mailer_id: int, update_data: dict) -> Mailer:
        mailer = self.get_by_id(db, mailer_id)
        if not mailer:
            raise ValueError("Mailer not found")
        effective_type = update_data.get("type", mailer.type)
        if effective_type == "manual" and update_data.get("body"):
            update_data["body"] = sanitize_html(update_data["body"])
        for field, value in update_data.items():
            setattr(mailer, field, value)
        db.commit()
        db.refresh(mailer)
        return mailer

    def delete(self, db: Session, mailer_id: int) -> None:
        mailer = self.get_by_id(db, mailer_id)
        if not mailer:
            raise ValueError("Mailer not found")
        db.delete(mailer)
        db.commit()
