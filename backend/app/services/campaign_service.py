"""Campaign CRUD business logic."""

from datetime import datetime, timedelta

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientList,
    CampaignSequenceStage,
    Recipient,
    RecipientGroup,
    Template,
)
from app.schemas.schemas import CampaignCreate, CampaignSequenceStageCreate, CampaignUpdate
from app.services.app_settings_service import AppSettingsService
from app.utils.helpers import sanitize_html, sanitize_manual_body, utc_now


app_settings_service = AppSettingsService()

# Statuses that must never receive another automated follow-up.
_TERMINAL_STATUSES = frozenset({"replied", "suppressed", "bounced", "invalid_email"})
# Statuses that count as "initial email already went out".
_SENT_STATUSES = frozenset({"sent", "delivered", "opened", "clicked", "out_of_office"})


def derive_follow_up_state(cr: CampaignRecipient) -> tuple[str, str]:
    """Return (state, human_label) for UI without renaming stored status."""
    if cr.status in {"replied", "bounced", "suppressed", "invalid_email"}:
        if cr.replied_at or cr.status == "replied":
            return "cancelled", "No follow-up"
        return "cancelled", "Follow-up cancelled"
    if cr.next_send_at is not None and cr.status not in _TERMINAL_STATUSES:
        when = cr.next_send_at.strftime("%d %b %Y") if hasattr(cr.next_send_at, "strftime") else str(cr.next_send_at)
        return "scheduled", f"Follow-up scheduled — {when}"
    if cr.current_stage and cr.current_stage >= 1:
        when = ""
        if cr.last_sent_at:
            when = f" — {cr.last_sent_at.strftime('%d %b %Y')}"
        return "sent", f"Follow-up sent{when}"
    return "none", "No follow-up"


class CampaignService:
    def create(self, db: Session, data: CampaignCreate, user_id: int | None = None, org_id: str | None = None) -> Campaign:
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
            org_id=org_id,
            scheduled_at=data.scheduled_at,
            use_recipient_timezone=data.use_recipient_timezone,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, org_id: str | None = None) -> list[Campaign]:
        query = db.query(Campaign)
        if org_id:
            query = query.filter(Campaign.org_id == org_id)
        return (
            query
            .order_by(Campaign.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_id(self, db: Session, campaign_id: int, org_id: str | None = None) -> Campaign | None:
        query = db.query(Campaign).filter(Campaign.id == campaign_id)
        if org_id:
            query = query.filter(Campaign.org_id == org_id)
        return query.first()

    def search_for_update(self, db: Session, q: str = "", limit: int = 100) -> list[Campaign]:
        """Campaigns for the Update list picker — by name/ID or recipient email."""
        term = (q or "").strip()
        if not term:
            return self.get_all(db, skip=0, limit=limit)

        like = f"%{term}%"
        by_name = (
            db.query(Campaign)
            .filter(
                or_(
                    Campaign.campaign_name.ilike(like),
                    Campaign.campaign_id.ilike(like),
                )
            )
            .all()
        )
        by_email = (
            db.query(Campaign)
            .join(CampaignRecipient, CampaignRecipient.campaign_id == Campaign.id)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(
                or_(
                    Recipient.email.ilike(like),
                    Recipient.name.ilike(like),
                )
            )
            .distinct()
            .all()
        )
        by_id: dict[int, Campaign] = {}
        for c in by_name + by_email:
            by_id[c.id] = c
        return sorted(
            by_id.values(),
            key=lambda c: c.created_at.timestamp() if c.created_at else 0,
            reverse=True,
        )[:limit]

    def list_emails_for_update(self, db: Session, q: str = "", limit: int = 200) -> list[dict]:
        """One card per email — lists every campaign that email was successfully sent in."""
        visible = {"sent", "delivered", "opened", "clicked", "replied", "out_of_office"}
        term = (q or "").strip()

        query = (
            db.query(CampaignRecipient, Recipient, Campaign)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
            .filter(CampaignRecipient.status.in_(visible))
        )
        if term:
            like = f"%{term}%"
            query = query.filter(
                or_(
                    Recipient.email.ilike(like),
                    Recipient.name.ilike(like),
                    Recipient.company.ilike(like),
                    Campaign.campaign_name.ilike(like),
                    Campaign.campaign_id.ilike(like),
                )
            )

        rows = query.order_by(CampaignRecipient.last_sent_at.desc()).all()

        by_email: dict[str, dict] = {}
        for cr, recipient, campaign in rows:
            key = (recipient.email or "").strip().lower()
            if not key:
                continue
            card = by_email.get(key)
            if not card:
                card = {
                    "recipient_id": recipient.id,
                    "name": recipient.name,
                    "email": recipient.email,
                    "company": recipient.company,
                    "designation": recipient.designation,
                    "campaigns": [],
                }
                by_email[key] = card

            _, follow_label = derive_follow_up_state(cr)
            # Prefer the most recently used recipient row if duplicates exist
            card["recipient_id"] = recipient.id
            card["name"] = recipient.name or card["name"]
            card["company"] = recipient.company or card["company"]
            card["designation"] = recipient.designation or card["designation"]
            # Skip duplicate campaign entries for same email
            if any(m["campaign_id"] == campaign.id for m in card["campaigns"]):
                continue
            card["campaigns"].append(
                {
                    "campaign_id": campaign.id,
                    "campaign_name": campaign.campaign_name,
                    "campaign_code": campaign.campaign_id,
                    "status": cr.status,
                    "last_sent_at": cr.last_sent_at,
                    "follow_up_label": follow_label,
                    "current_stage": cr.current_stage or 0,
                    "follow_up_sent": bool(cr.current_stage and cr.current_stage >= 1),
                }
            )

        items: list[dict] = []
        for card in by_email.values():
            campaigns = card["campaigns"]
            statuses = {m["status"] for m in campaigns}
            if statuses == {"replied"}:
                display_status = "replied"
            elif "replied" in statuses and len(statuses) > 1:
                display_status = "mixed"
            else:
                display_status = next(iter(statuses)) if len(statuses) == 1 else "sent"
            unreplied = sum(1 for m in campaigns if m["status"] != "replied")
            follow_up_sent_count = sum(1 for m in campaigns if m.get("follow_up_sent"))
            marked_updated_count = sum(1 for m in campaigns if m["status"] == "replied")
            items.append(
                {
                    **card,
                    "campaign_count": len(campaigns),
                    "follow_up_sent_count": follow_up_sent_count,
                    "marked_updated_count": marked_updated_count,
                    "display_status": display_status,
                    "unreplied_campaign_count": unreplied,
                }
            )

        items.sort(key=lambda c: c["campaign_count"], reverse=True)
        return items[:limit]

    def mark_email_replied(
        self,
        db: Session,
        email: str,
        campaign_ids: list[int] | None = None,
    ) -> dict:
        """Mark replied for this email across all (or selected) campaigns; cancel follow-ups."""
        email_norm = (email or "").strip().lower()
        if not email_norm:
            raise ValueError("email is required")

        query = (
            db.query(CampaignRecipient)
            .join(Recipient, Recipient.id == CampaignRecipient.recipient_id)
            .filter(func.lower(Recipient.email) == email_norm)
        )
        if campaign_ids:
            query = query.filter(CampaignRecipient.campaign_id.in_(campaign_ids))

        rows = query.all()
        if not rows:
            raise ValueError("No campaign recipients found for this email")

        now = utc_now()
        updated = 0
        skipped = 0
        for cr in rows:
            if cr.status == "replied":
                skipped += 1
                continue
            cr.status = "replied"
            cr.replied_at = now
            cr.next_send_at = None
            updated += 1
        db.commit()
        return {"updated": updated, "skipped": skipped}

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

    def update(self, db: Session, campaign_id: int, data: CampaignUpdate, org_id: str | None = None) -> Campaign:
        campaign = self.get_by_id(db, campaign_id, org_id=org_id)
        if not campaign:
            raise ValueError("Campaign not found")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(campaign, field, value)

        db.commit()
        db.refresh(campaign)
        return campaign

    def delete(self, db: Session, campaign_id: int, org_id: str | None = None) -> None:
        campaign = self.get_by_id(db, campaign_id, org_id=org_id)
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

    def mark_recipients_replied(
        self, db: Session, campaign_id: int, recipient_ids: list[int]
    ) -> dict:
        """Manually mark selected campaign recipients as replied; cancel pending follow-ups."""
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")
        if not recipient_ids:
            return {"updated": 0, "skipped": 0, "undo_items": []}

        rows = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.recipient_id.in_(recipient_ids),
            )
            .all()
        )
        now = utc_now()
        updated = 0
        undo_items: list[dict] = []
        for cr in rows:
            if cr.status == "replied":
                continue
            undo_items.append(
                {
                    "recipient_id": cr.recipient_id,
                    "previous_status": cr.status,
                    "previous_next_send_at": cr.next_send_at,
                }
            )
            cr.status = "replied"
            cr.replied_at = now
            cr.next_send_at = None
            updated += 1
        db.commit()
        skipped = len(recipient_ids) - updated
        return {"updated": updated, "skipped": max(0, skipped), "undo_items": undo_items}

    def undo_mark_recipients_replied(
        self, db: Session, campaign_id: int, items: list[dict]
    ) -> dict:
        """Restore recipients after a manual mark-replied, using captured previous state."""
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")
        if not items:
            return {"updated": 0, "skipped": 0}

        by_id = {item["recipient_id"]: item for item in items}
        rows = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.recipient_id.in_(list(by_id.keys())),
            )
            .all()
        )
        restored = 0
        skipped = 0
        for cr in rows:
            item = by_id.get(cr.recipient_id)
            if not item:
                continue
            if cr.status != "replied":
                skipped += 1
                continue
            cr.status = item.get("previous_status") or "sent"
            cr.replied_at = None
            cr.next_send_at = item.get("previous_next_send_at")
            restored += 1
        db.commit()
        return {"updated": restored, "skipped": skipped}

    def schedule_followups(
        self,
        db: Session,
        campaign_id: int,
        scheduled_at: datetime,
        *,
        recipient_ids: list[int] | None = None,
        all_non_replied: bool = False,
        sender_user_id: int | None = None,
    ) -> dict:
        """Set absolute next_send_at for eligible non-replied recipients.

        Content is taken from the campaign's next sequence stage at send time
        (existing process_due_followups). Requires at least one sequence stage.
        """
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")

        stages = self.list_sequence_stages(db, campaign_id)
        if not stages:
            raise ValueError(
                "Add at least one follow-up stage on the Follow-up Sequence tab before scheduling"
            )

        if scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone")
        if scheduled_at <= utc_now():
            raise ValueError("scheduled_at must be in the future")

        if not all_non_replied and not recipient_ids:
            raise ValueError("Provide recipient_ids or set all_non_replied=true")

        query = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id)
        if all_non_replied:
            query = query.filter(CampaignRecipient.status.notin_(_TERMINAL_STATUSES))
            query = query.filter(CampaignRecipient.status.in_(_SENT_STATUSES))
        else:
            query = query.filter(CampaignRecipient.recipient_id.in_(recipient_ids or []))

        rows = query.all()
        scheduled = 0
        skipped = 0
        for cr in rows:
            if cr.status in _TERMINAL_STATUSES:
                skipped += 1
                continue
            if cr.status not in _SENT_STATUSES:
                skipped += 1
                continue
            # Must have a next stage defined for their current progress.
            next_order = cr.current_stage + 1
            has_stage = any(s.stage_order == next_order for s in stages)
            if not has_stage:
                skipped += 1
                continue
            cr.next_send_at = scheduled_at
            if sender_user_id is not None:
                cr.sender_user_id = sender_user_id
            scheduled += 1

        db.commit()
        return {"scheduled": scheduled, "skipped": skipped, "scheduled_at": scheduled_at}

    def cancel_followups(
        self,
        db: Session,
        campaign_id: int,
        *,
        recipient_ids: list[int] | None = None,
        all_scheduled: bool = False,
    ) -> dict:
        """Clear next_send_at for scheduled follow-ups on this campaign only.

        Does not change recipient status (e.g. leaves status as sent). Skips
        terminal rows and rows with no pending next_send_at.
        """
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")

        if not all_scheduled and not recipient_ids:
            raise ValueError("Provide recipient_ids or set all_scheduled=true")

        query = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id)
        if all_scheduled:
            query = query.filter(
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.status.notin_(_TERMINAL_STATUSES),
            )
        else:
            query = query.filter(CampaignRecipient.recipient_id.in_(recipient_ids or []))

        cancelled = 0
        skipped = 0
        for cr in query.all():
            if cr.status in _TERMINAL_STATUSES:
                skipped += 1
                continue
            if cr.next_send_at is None:
                skipped += 1
                continue
            cr.next_send_at = None
            cancelled += 1

        db.commit()
        return {"cancelled": cancelled, "skipped": skipped}

    def recipient_stats(self, db: Session, campaign_id: int) -> dict:
        rows = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == campaign_id)
            .all()
        )
        sent = 0
        replied = 0
        no_reply = 0
        follow_up_scheduled = 0
        follow_up_sent = 0
        follow_up_cancelled = 0
        bounced = 0
        not_contacted = 0

        for cr in rows:
            if cr.status in {"not_contacted", "queued"}:
                not_contacted += 1

            contacted = cr.last_sent_at is not None or cr.status in (
                _SENT_STATUSES | {"replied", "bounced", "suppressed", "invalid_email"}
            )
            if contacted:
                sent += 1

            if cr.status == "replied":
                replied += 1
                follow_up_cancelled += 1
            elif cr.status in {"bounced", "suppressed", "invalid_email"}:
                bounced += 1
                follow_up_cancelled += 1
            elif cr.next_send_at is not None and cr.status not in _TERMINAL_STATUSES:
                follow_up_scheduled += 1
                no_reply += 1
            elif cr.current_stage >= 1:
                follow_up_sent += 1
                no_reply += 1
            elif cr.status in _SENT_STATUSES:
                no_reply += 1

        return {
            "total": len(rows),
            "sent": sent,
            "replied": replied,
            "no_reply": no_reply,
            "follow_up_scheduled": follow_up_scheduled,
            "follow_up_sent": follow_up_sent,
            "follow_up_cancelled": follow_up_cancelled,
            "bounced": bounced,
            "not_contacted": not_contacted,
        }
