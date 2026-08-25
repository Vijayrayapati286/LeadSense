"""Campaign CRUD business logic."""

from datetime import timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientList,
    EngagementStudioList,
    EngagementStudioStage,
    Mailer,
    Recipient,
    RecipientGroup,
    Template,
)
from app.schemas.schemas import CampaignCreate, CampaignUpdate, EngagementStudioStageCreate
from app.services.app_settings_service import AppSettingsService
from app.utils.helpers import sanitize_html, sanitize_manual_body


app_settings_service = AppSettingsService()

# Statuses that stop automated follow-ups — kept in sync with
# scheduler_service.TERMINAL_STATUSES (duplicated here rather than imported to
# avoid a service-to-service import for one constant).
_TERMINAL_STATUSES = {"replied", "suppressed", "bounced", "invalid_email"}


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
        # A partial update might touch `body` without `type` in the payload —
        # fall back to the stored type so a body edit on an existing Manual
        # template still gets sanitized.
        effective_type = update_data.get("type", template.type)
        if effective_type == "manual" and update_data.get("body"):
            update_data["body"] = sanitize_html(update_data["body"])
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

        template_data = sanitize_manual_body(template_data)
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
        its template_id — this is what makes a prospect send with a specific
        template rather than the campaign's primary one.

        List membership ("By List" browsing) is tracked separately, in
        CampaignRecipientList, and is purely additive: tagging a recipient
        into a list here never removes them from a list they're already in
        for this campaign, so a recipient can legitimately belong to several
        lists in the same campaign at once. It's scoped strictly to this
        campaign's own rows (not raw RecipientGroupMember membership) so a
        recipient who happens to be a member of an unrelated list elsewhere
        — e.g. via a reused list name or an already-listed email added
        individually — doesn't leak that other list into this campaign's
        "By List" view. The recipient's actual send state (status/template)
        still lives on the one CampaignRecipient row below, since a
        recipient only ever receives one email per campaign regardless of
        how many lists they're tagged under."""
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
                exists = (
                    db.query(CampaignRecipientList)
                    .filter(
                        CampaignRecipientList.campaign_id == campaign_id,
                        CampaignRecipientList.recipient_id == recipient_id,
                        CampaignRecipientList.group_id == group_id,
                    )
                    .first()
                )
                if not exists:
                    db.add(CampaignRecipientList(campaign_id=campaign_id, recipient_id=recipient_id, group_id=group_id))
            tagged += 1
        db.commit()
        return tagged

    def _list_member_recipient_ids(self, db: Session, campaign_id: int, group_id: int):
        """Recipient ids tagged into `group_id` for `campaign_id`, per the
        additive CampaignRecipientList membership table — usable directly as
        an `.in_()` subquery."""
        return db.query(CampaignRecipientList.recipient_id).filter(
            CampaignRecipientList.campaign_id == campaign_id,
            CampaignRecipientList.group_id == group_id,
        )

    def list_campaign_lists(self, db: Session, campaign_id: int) -> list[dict]:
        """Every list (RecipientGroup) this campaign's prospects were tagged
        under, with a total, sent count, and representative template — the
        "By List" browse mode's summary cards. Membership comes from
        CampaignRecipientList (see tag_recipients' docstring: additive per
        campaign, so a recipient can show under more than one list here),
        while send state (status/template) is read off the recipient's one
        CampaignRecipient row for this campaign."""
        rows = (
            db.query(
                CampaignRecipientList.group_id,
                RecipientGroup.name,
                func.count(func.distinct(CampaignRecipientList.recipient_id)).label("total"),
                func.sum(case((CampaignRecipient.status == "sent", 1), else_=0)).label("sent_count"),
            )
            .join(RecipientGroup, RecipientGroup.id == CampaignRecipientList.group_id)
            .join(
                CampaignRecipient,
                (CampaignRecipient.campaign_id == CampaignRecipientList.campaign_id)
                & (CampaignRecipient.recipient_id == CampaignRecipientList.recipient_id),
            )
            .filter(CampaignRecipientList.campaign_id == campaign_id)
            .group_by(CampaignRecipientList.group_id, RecipientGroup.name)
            .order_by(RecipientGroup.name)
            .all()
        )

        results = []
        for group_id, name, total, sent_count in rows:
            member_ids = self._list_member_recipient_ids(db, campaign_id, group_id)
            # A representative template for the list — retag_list keeps every
            # member's row on the same template_id, so any one's value works.
            sample = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id.in_(member_ids))
                .first()
            )
            # Earliest pending send time among this list's queued rows — what
            # the calendar icon shows as "Scheduled for ..." on the card.
            earliest_queued = (
                db.query(func.min(CampaignRecipient.next_send_at))
                .filter(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.recipient_id.in_(member_ids),
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
        member_ids = self._list_member_recipient_ids(db, campaign_id, group_id)
        rows = (
            db.query(CampaignRecipient, Recipient)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.recipient_id.in_(member_ids),
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
        member_ids = self._list_member_recipient_ids(db, campaign_id, group_id)
        return (
            db.query(CampaignRecipient, Recipient)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id.in_(member_ids))
            .order_by(Recipient.name)
            .all()
        )

    def retag_list(self, db: Session, campaign_id: int, group_id: int, template_id: int | None) -> int:
        member_ids = self._list_member_recipient_ids(db, campaign_id, group_id)
        rows = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id.in_(member_ids))
            .all()
        )
        for cr in rows:
            cr.template_id = template_id
        db.commit()
        return len(rows)

    def list_engagement_studio_stages(self, db: Session, campaign_id: int) -> list[EngagementStudioStage]:
        return (
            db.query(EngagementStudioStage)
            .filter(EngagementStudioStage.campaign_id == campaign_id)
            .order_by(EngagementStudioStage.stage_order)
            .all()
        )

    def create_engagement_studio_stage(
        self, db: Session, campaign_id: int, data: EngagementStudioStageCreate
    ) -> EngagementStudioStage:
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")

        existing = (
            db.query(EngagementStudioStage)
            .filter(
                EngagementStudioStage.campaign_id == campaign_id,
                EngagementStudioStage.stage_order == data.stage_order,
            )
            .first()
        )
        if existing:
            raise ValueError(f"Stage order {data.stage_order} already exists for this campaign")

        if data.mailer_id is not None:
            if not db.query(Mailer).filter(Mailer.id == data.mailer_id).first():
                raise ValueError("Template library entry not found")
        elif not (data.subject and data.body):
            raise ValueError("Provide a mailer_id (template library) or both subject and body")

        stage = EngagementStudioStage(campaign_id=campaign_id, **data.model_dump())
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage

    def update_engagement_studio_stage(self, db: Session, stage_id: int, update_data: dict) -> EngagementStudioStage:
        stage = db.query(EngagementStudioStage).filter(EngagementStudioStage.id == stage_id).first()
        if not stage:
            raise ValueError("Engagement Studio stage not found")
        if "mailer_id" in update_data and update_data["mailer_id"] is not None:
            if not db.query(Mailer).filter(Mailer.id == update_data["mailer_id"]).first():
                raise ValueError("Template library entry not found")
        for field, value in update_data.items():
            setattr(stage, field, value)
        db.commit()
        db.refresh(stage)
        return stage

    def delete_engagement_studio_stage(self, db: Session, stage_id: int) -> None:
        stage = db.query(EngagementStudioStage).filter(EngagementStudioStage.id == stage_id).first()
        if not stage:
            raise ValueError("Engagement Studio stage not found")
        db.delete(stage)
        db.commit()

    def get_engagement_studio_lists(self, db: Session, campaign_id: int) -> list[int]:
        return [
            row.group_id
            for row in db.query(EngagementStudioList.group_id)
            .filter(EngagementStudioList.campaign_id == campaign_id)
            .all()
        ]

    def set_engagement_studio_lists(self, db: Session, campaign_id: int, group_ids: list[int]) -> list[int]:
        """Replace-all: only lists already tagged into this campaign (via
        CampaignRecipientList / list_campaign_lists) may be selected."""
        valid_group_ids = {row["group_id"] for row in self.list_campaign_lists(db, campaign_id)}
        unknown = set(group_ids) - valid_group_ids
        if unknown:
            raise ValueError(f"List(s) {sorted(unknown)} are not part of this campaign")

        db.query(EngagementStudioList).filter(EngagementStudioList.campaign_id == campaign_id).delete()
        for group_id in group_ids:
            db.add(EngagementStudioList(campaign_id=campaign_id, group_id=group_id))
        db.commit()
        return self.get_engagement_studio_lists(db, campaign_id)

    def get_engagement_studio_overview(self, db: Session, campaign_id: int) -> dict:
        """Cohort breakdown for the Engagement Studio's configured scope (its
        selected prospect lists, or every campaign prospect if none are
        selected — same backward-compatible default as the scheduler uses)."""
        group_ids = self.get_engagement_studio_lists(db, campaign_id)

        query = db.query(CampaignRecipient).join(Recipient, Recipient.id == CampaignRecipient.recipient_id).filter(
            CampaignRecipient.campaign_id == campaign_id
        )
        if group_ids:
            member_ids = (
                db.query(CampaignRecipientList.recipient_id)
                .filter(
                    CampaignRecipientList.campaign_id == campaign_id,
                    CampaignRecipientList.group_id.in_(group_ids),
                )
                .distinct()
            )
            query = query.filter(CampaignRecipient.recipient_id.in_(member_ids))

        rows = query.filter(CampaignRecipient.status != "not_contacted").all()

        # "Hot" is the auto-tag a reply sets (event_service.handle_reply) —
        # everything else (Cold, an untagged not-yet-evaluated row, or any
        # manual Warm/Negative not yet overridden by the scheduler) counts as
        # still non-responsive, since only a reply exits the sequence.
        total = len(rows)
        responded = len([
            cr for cr in rows if cr.status == "replied" or cr.recipient.response_tag == "Hot"
        ])
        non_responsive_rows = [
            cr for cr in rows if cr.status not in _TERMINAL_STATUSES and cr.recipient.response_tag != "Hot"
        ]

        return {
            "total": total,
            "responded": responded,
            "non_responsive": len(non_responsive_rows),
            "non_responsive_recipients": non_responsive_rows[:200],
        }
