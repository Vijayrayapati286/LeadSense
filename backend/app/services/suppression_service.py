"""Suppression list / blacklist business logic.

Entries are never hard-deleted — an admin override sets `overridden_at`
instead, preserving the historical record while allowing the address to be
used again. `is_suppressed`/`list` only consider entries where
`overridden_at is None` ("currently active").
"""

from sqlalchemy.orm import Session

from app.models import Recipient, SuppressionEntry
from app.utils.helpers import utc_now


class SuppressionService:
    def add(
        self,
        db: Session,
        recipient: Recipient,
        reason: str,
        detail: str | None = None,
        campaign_id: int | None = None,
        bounce_type: str | None = None,
        smtp_code: str | None = None,
    ) -> SuppressionEntry:
        recipient.is_suppressed = True
        recipient.suppression_reason = reason

        entry = SuppressionEntry(
            email=recipient.email,
            company=recipient.company,
            reason=reason,
            bounce_type=bounce_type,
            smtp_code=smtp_code,
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
        bounce_type: str | None = None,
        smtp_code: str | None = None,
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
            bounce_type=bounce_type,
            smtp_code=smtp_code,
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
            .filter(SuppressionEntry.email == email, SuppressionEntry.overridden_at.is_(None))
            .first()
            is not None
        )

    def list(
        self, db: Session, page: int = 1, page_size: int = 10, search: str = ""
    ) -> tuple[list[SuppressionEntry], int]:
        query = db.query(SuppressionEntry).filter(SuppressionEntry.overridden_at.is_(None))
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

    def override(self, db: Session, entry_id: int) -> SuppressionEntry:
        """Admin override: clear the suppression for this entry's email so it
        can be used again — e.g. after confirming a bounce was a fluke or the
        mailbox issue was resolved. The entry itself is kept (not deleted) as
        a historical record; only `overridden_at` is set."""
        entry = db.query(SuppressionEntry).filter(SuppressionEntry.id == entry_id).first()
        if not entry:
            raise ValueError("Suppression entry not found")
        if entry.overridden_at is not None:
            raise ValueError("This entry has already been overridden")

        entry.overridden_at = utc_now()

        # Only clear the Recipient-level flag if no OTHER active suppression
        # entry still exists for this email (e.g. hard-bounced twice).
        still_active = (
            db.query(SuppressionEntry)
            .filter(
                SuppressionEntry.email == entry.email,
                SuppressionEntry.overridden_at.is_(None),
                SuppressionEntry.id != entry.id,
            )
            .first()
        )
        if not still_active:
            recipients = db.query(Recipient).filter(Recipient.email == entry.email).all()
            for recipient in recipients:
                recipient.is_suppressed = False
                recipient.suppression_reason = None
                recipient.soft_bounce_count = 0

        db.commit()
        db.refresh(entry)
        return entry
