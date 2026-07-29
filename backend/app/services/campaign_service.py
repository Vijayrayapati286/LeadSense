"""Campaign CRUD business logic."""

from datetime import timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import Campaign, CampaignRecipient, CampaignSequenceStage, Recipient, RecipientGroup, Template
from app.schemas.schemas import CampaignCreate, CampaignSequenceStageCreate, CampaignUpdate
from app.services.app_settings_service import AppSettingsService


app_settings_service = AppSettingsService()


class CampaignService:
    def create(self, db: Session, data: CampaignCreate, user_id: int | None = None) -> Campaign:
        existing = db.query(Campaign).filter(Campaign.campaign_id == data.campaign_id).first()
        if existing:
            raise ValueError(f"Campaign ID '{data.campaign_id}' already exists")

        campaign = Campaign(
            campaign_name=data.campaign_name,
            campaign_id=data.campaign_id,
            description=data.description,
            owner=data.owner,
            department=data.department,
            target_audience=data.target_audience,
            subject=data.subject,
            status=data.status,
            user_id=user_id,
            scheduled_at=data.scheduled_at,
            use_recipient_timezone=data.use_recipient_timezone,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> list[Campaign]:
        return (
            db.query(Campaign)
            .order_by(Campaign.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_id(self, db: Session, campaign_id: int) -> Campaign | None:
        return db.query(Campaign).filter(Campaign.id == campaign_id).first()

    def get_template(self, db: Session, campaign_id: int) -> Template | None:
        """The campaign's primary template — the first one created. With
        multiple templates now supported, this stays the stable "default"
        used wherever only a single template makes sense (e.g. the wizard's
        edit-mode load, campaign.subject)."""
        return (
            db.query(Template)
            .filter(Template.campaign_id == campaign_id)
            .order_by(Template.created_at.asc())
            .first()
        )

    def list_templates(self, db: Session, campaign_id: int) -> list[Template]:
        return (
            db.query(Template)
            .filter(Template.campaign_id == campaign_id)
            .order_by(Template.created_at.asc())
            .all()
        )

    def delete_template(self, db: Session, template_id: int) -> None:
        template = db.query(Template).filter(Template.id == template_id).first()
        if not template:
            raise ValueError("Template not found")
        db.delete(template)
        db.commit()

    def update_template(self, db: Session, template_id: int, update_data: dict) -> Template:
        template = db.query(Template).filter(Template.id == template_id).first()
        if not template:
            raise ValueError("Template not found")
        for field, value in update_data.items():
            setattr(template, field, value)
        db.commit()
        db.refresh(template)
        return template

    def update(self, db: Session, campaign_id: int, data: CampaignUpdate) -> Campaign:
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(campaign, field, value)

        db.commit()
        db.refresh(campaign)
        return campaign

    def delete(self, db: Session, campaign_id: int) -> None:
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")
        db.delete(campaign)
        db.commit()

    def save_template(self, db: Session, campaign_id: int, template_data: dict) -> Template:
        """Add a new template to the campaign — a campaign can hold several,
        each independently tag-able to a prospect list via
        CampaignRecipient.template_id."""
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        template = Template(
            campaign_id=campaign_id,
            name=template_data.get("name") or f"Template {len(campaign.templates) + 1}",
            type=template_data["type"],
            subject=template_data["subject"],
            body=template_data["body"],
            closing=template_data.get("closing"),
            cta=template_data.get("cta"),
        )
        db.add(template)

        # Only backfill campaign.subject once, from the first template — a
        # stable label rather than whichever template was saved most recently.
        if not campaign.subject and template_data.get("subject"):
            campaign.subject = template_data["subject"]

        db.commit()
        db.refresh(template)
        return template

    def tag_recipients(
        self,
        db: Session,
        campaign_id: int,
        recipient_ids: list[int],
        template_id: int | None,
        group_id: int | None = None,
    ) -> int:
        """Get-or-create the CampaignRecipient row for each recipient and set
        its template_id (and group_id, when tagging happened as part of an
        Upload Excel / Add Manually under a named list) — this is what makes
        a prospect list send with a specific template rather than the
        campaign's primary one, and what "By List" browsing groups on."""
        tagged = 0
        for recipient_id in recipient_ids:
            cr = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id == recipient_id)
                .first()
            )
            if not cr:
                cr = CampaignRecipient(campaign_id=campaign_id, recipient_id=recipient_id)
                db.add(cr)
            cr.template_id = template_id
            if group_id is not None:
                cr.group_id = group_id
            tagged += 1
        db.commit()
        return tagged

    def list_campaign_lists(self, db: Session, campaign_id: int) -> list[dict]:
        """Every list (RecipientGroup) this campaign's prospects were tagged
        under, with a total, sent count, and representative template — the
        "By List" browse mode's summary cards."""
        rows = (
            db.query(
                CampaignRecipient.group_id,
                RecipientGroup.name,
                func.count(CampaignRecipient.id).label("total"),
                func.sum(case((CampaignRecipient.status == "sent", 1), else_=0)).label("sent_count"),
            )
            .join(RecipientGroup, RecipientGroup.id == CampaignRecipient.group_id)
            .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.group_id.isnot(None))
            .group_by(CampaignRecipient.group_id, RecipientGroup.name)
            .order_by(RecipientGroup.name)
            .all()
        )

        results = []
        for group_id, name, total, sent_count in rows:
            # A representative template for the list — retag_list keeps every
            # row in a group on the same template_id, so any row's value works.
            sample = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.group_id == group_id)
                .first()
            )
            # Earliest pending send time among this list's queued rows — what
            # the calendar icon shows as "Scheduled for ..." on the card.
            earliest_queued = (
                db.query(func.min(CampaignRecipient.next_send_at))
                .filter(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.group_id == group_id,
                    CampaignRecipient.status == "queued",
                    CampaignRecipient.next_send_at.isnot(None),
                )
                .scalar()
            )
            results.append({
                "group_id": group_id,
                "name": name,
                "total": total,
                "sent_count": sent_count or 0,
                "template_id": sample.template_id if sample else None,
                "scheduled_at": earliest_queued,
            })
        return results

    def schedule_list(self, db: Session, campaign_id: int, group_id: int, scheduled_at, sender_user_id: int) -> dict:
        """Queue every not-yet-sent prospect in this list to go out starting
        at scheduled_at, staggered by the configured send interval — reuses
        the same CampaignRecipient.next_send_at queue the regular Send flow
        writes to, so process_queued_initial_sends (scheduler_service.py)
        picks these up and sends them automatically with no extra job."""
        rows = (
            db.query(CampaignRecipient, Recipient)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.group_id == group_id,
                CampaignRecipient.status != "sent",
            )
            .all()
        )

        skipped_suppressed = len([cr for cr, r in rows if r.is_suppressed])
        schedulable = [cr for cr, r in rows if not r.is_suppressed]

        interval_seconds = app_settings_service.get(db).send_interval_seconds
        for index, cr in enumerate(schedulable):
            cr.status = "queued"
            cr.next_send_at = scheduled_at + timedelta(seconds=index * interval_seconds)
            cr.sender_user_id = sender_user_id
        db.commit()

        return {
            "scheduled": len(schedulable),
            "skipped_suppressed": skipped_suppressed,
            "scheduled_at": scheduled_at,
        }

    def get_list_members(
        self, db: Session, campaign_id: int, group_id: int
    ) -> list[tuple[CampaignRecipient, Recipient]]:
        return (
            db.query(CampaignRecipient, Recipient)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.group_id == group_id)
            .order_by(Recipient.name)
            .all()
        )

    def retag_list(self, db: Session, campaign_id: int, group_id: int, template_id: int | None) -> int:
        rows = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.group_id == group_id)
            .all()
        )
        for cr in rows:
            cr.template_id = template_id
        db.commit()
        return len(rows)

    def list_sequence_stages(self, db: Session, campaign_id: int) -> list[CampaignSequenceStage]:
        return (
            db.query(CampaignSequenceStage)
            .filter(CampaignSequenceStage.campaign_id == campaign_id)
            .order_by(CampaignSequenceStage.stage_order)
            .all()
        )

    def create_sequence_stage(
        self, db: Session, campaign_id: int, data: CampaignSequenceStageCreate
    ) -> CampaignSequenceStage:
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")

        existing = (
            db.query(CampaignSequenceStage)
            .filter(
                CampaignSequenceStage.campaign_id == campaign_id,
                CampaignSequenceStage.stage_order == data.stage_order,
            )
            .first()
        )
        if existing:
            raise ValueError(f"Stage order {data.stage_order} already exists for this campaign")

        stage = CampaignSequenceStage(campaign_id=campaign_id, **data.model_dump())
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage

    def update_sequence_stage(self, db: Session, stage_id: int, update_data: dict) -> CampaignSequenceStage:
        stage = db.query(CampaignSequenceStage).filter(CampaignSequenceStage.id == stage_id).first()
        if not stage:
            raise ValueError("Sequence stage not found")
        for field, value in update_data.items():
            setattr(stage, field, value)
        db.commit()
        db.refresh(stage)
        return stage

    def delete_sequence_stage(self, db: Session, stage_id: int) -> None:
        stage = db.query(CampaignSequenceStage).filter(CampaignSequenceStage.id == stage_id).first()
        if not stage:
            raise ValueError("Sequence stage not found")
        db.delete(stage)
        db.commit()
