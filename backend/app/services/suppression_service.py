"""Suppression list / blacklist business logic.

Entries here are append-only and view-only from the UI — once a recipient is
suppressed there is no endpoint to un-suppress or delete the audit entry.
"""

from sqlalchemy.orm import Session

from app.models import Recipient, SuppressionEntry


class SuppressionService:
    def add(
        self,
        db: Session,
        recipient: Recipient,
        reason: str,
        detail: str | None = None,
        campaign_id: int | None = None,
    ) -> SuppressionEntry:
        recipient.is_suppressed = True
        recipient.suppression_reason = reason

        entry = SuppressionEntry(
            email=recipient.email,
            company=recipient.company,
            reason=reason,
            campaign_id=campaign_id,
            recipient_id=recipient.id,
            detail=detail,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def add_by_email(
        self,
        db: Session,
        email: str,
        reason: str,
        detail: str | None = None,
        campaign_id: int | None = None,
    ) -> SuppressionEntry | None:
        """Suppress every recipient row matching this email (there is no unique
        constraint on Recipient.email), and always record one audit entry."""
        recipients = db.query(Recipient).filter(Recipient.email == email).all()
        for recipient in recipients:
            recipient.is_suppressed = True
            recipient.suppression_reason = reason

        entry = SuppressionEntry(
            email=email,
            company=recipients[0].company if recipients else None,
            reason=reason,
            campaign_id=campaign_id,
            recipient_id=recipients[0].id if recipients else None,
            detail=detail,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def is_suppressed(self, db: Session, email: str) -> bool:
        return (
            db.query(SuppressionEntry)
            .filter(SuppressionEntry.email == email)
            .first()
            is not None
        )

    def list(
        self, db: Session, page: int = 1, page_size: int = 10, search: str = ""
    ) -> tuple[list[SuppressionEntry], int]:
        query = db.query(SuppressionEntry)
        if search:
            term = f"%{search}%"
            query = query.filter(
                (SuppressionEntry.email.ilike(term)) | (SuppressionEntry.company.ilike(term))
            )

        total = query.count()
        items = (
            query.order_by(SuppressionEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total
