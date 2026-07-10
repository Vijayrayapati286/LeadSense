"""Recipient group (team/list) business logic."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Recipient, RecipientGroup, RecipientGroupMember


class RecipientGroupService:
    def create(self, db: Session, name: str, description: str | None = None) -> RecipientGroup:
        existing = db.query(RecipientGroup).filter(RecipientGroup.name == name).first()
        if existing:
            raise ValueError(f"Group '{name}' already exists")

        group = RecipientGroup(name=name, description=description)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    def get_or_create(self, db: Session, name: str) -> RecipientGroup:
        group = db.query(RecipientGroup).filter(RecipientGroup.name == name).first()
        if group:
            return group
        group = RecipientGroup(name=name)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    def list_groups(self, db: Session, search: str = "") -> list[dict]:
        query = db.query(
            RecipientGroup,
            func.count(RecipientGroupMember.recipient_id).label("prospect_count"),
        ).outerjoin(RecipientGroupMember, RecipientGroupMember.group_id == RecipientGroup.id)

        if search:
            query = query.filter(RecipientGroup.name.ilike(f"%{search}%"))

        query = query.group_by(RecipientGroup.id).order_by(RecipientGroup.name)

        results = []
        for group, count in query.all():
            results.append({"group": group, "prospect_count": count})
        return results

    def get_by_id(self, db: Session, group_id: int) -> RecipientGroup | None:
        return db.query(RecipientGroup).filter(RecipientGroup.id == group_id).first()

    def rename(self, db: Session, group_id: int, name: str | None, description: str | None) -> RecipientGroup:
        group = self.get_by_id(db, group_id)
        if not group:
            raise ValueError("Group not found")
        if name is not None:
            group.name = name
        if description is not None:
            group.description = description
        db.commit()
        db.refresh(group)
        return group

    def delete(self, db: Session, group_id: int) -> None:
        group = self.get_by_id(db, group_id)
        if not group:
            raise ValueError("Group not found")
        db.delete(group)
        db.commit()

    def add_members(self, db: Session, group_id: int, recipient_ids: list[int]) -> int:
        group = self.get_by_id(db, group_id)
        if not group:
            raise ValueError("Group not found")

        existing_ids = {
            m.recipient_id
            for m in db.query(RecipientGroupMember).filter(RecipientGroupMember.group_id == group_id).all()
        }
        added = 0
        for recipient_id in recipient_ids:
            if recipient_id in existing_ids:
                continue
            db.add(RecipientGroupMember(group_id=group_id, recipient_id=recipient_id))
            existing_ids.add(recipient_id)
            added += 1
        db.commit()
        return added

    def remove_member(self, db: Session, group_id: int, recipient_id: int) -> None:
        db.query(RecipientGroupMember).filter(
            RecipientGroupMember.group_id == group_id,
            RecipientGroupMember.recipient_id == recipient_id,
        ).delete()
        db.commit()

    def get_members(
        self, db: Session, group_id: int, page: int = 1, page_size: int = 10, search: str = ""
    ) -> tuple[list[Recipient], int]:
        query = (
            db.query(Recipient)
            .join(RecipientGroupMember, RecipientGroupMember.recipient_id == Recipient.id)
            .filter(RecipientGroupMember.group_id == group_id)
        )
        if search:
            term = f"%{search}%"
            query = query.filter(
                (Recipient.name.ilike(term)) | (Recipient.email.ilike(term))
            )

        total = query.count()
        items = (
            query.order_by(Recipient.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total
