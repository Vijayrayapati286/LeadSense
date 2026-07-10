"""Tag business logic — lightweight labels (e.g. "Decision Maker") that can
be assigned to any recipient and combined with any other search filter."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import RecipientTag, Tag


class TagService:
    def get_or_create(self, db: Session, name: str) -> Tag:
        tag = db.query(Tag).filter(Tag.name == name).first()
        if tag:
            return tag
        tag = Tag(name=name)
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return tag

    def list_tags(self, db: Session, search: str = "") -> list[dict]:
        query = db.query(Tag, func.count(RecipientTag.recipient_id).label("recipient_count")).outerjoin(
            RecipientTag, RecipientTag.tag_id == Tag.id
        )
        if search:
            query = query.filter(Tag.name.ilike(f"%{search}%"))
        query = query.group_by(Tag.id).order_by(Tag.name)
        return [{"tag": tag, "recipient_count": count} for tag, count in query.all()]

    def delete(self, db: Session, tag_id: int) -> None:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise ValueError("Tag not found")
        db.delete(tag)
        db.commit()

    def assign(self, db: Session, tag_id: int, recipient_ids: list[int]) -> int:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise ValueError("Tag not found")

        existing_ids = {
            rt.recipient_id for rt in db.query(RecipientTag).filter(RecipientTag.tag_id == tag_id).all()
        }
        added = 0
        for recipient_id in recipient_ids:
            if recipient_id in existing_ids:
                continue
            db.add(RecipientTag(tag_id=tag_id, recipient_id=recipient_id))
            existing_ids.add(recipient_id)
            added += 1
        db.commit()
        return added

    def unassign(self, db: Session, tag_id: int, recipient_id: int) -> None:
        db.query(RecipientTag).filter(
            RecipientTag.tag_id == tag_id, RecipientTag.recipient_id == recipient_id
        ).delete()
        db.commit()
