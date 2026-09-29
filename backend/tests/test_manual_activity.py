"""Recording mail sent outside LeadSense stays on one campaign and does not queue a send."""

from datetime import datetime, timedelta, timezone

from app.database.connection import SessionLocal
from app.models import Campaign, CampaignRecipient, CampaignSequenceStage, EmailLog, Recipient, Template
from app.schemas.schemas import ManualContactInput, RecordManualActivityRequest
from app.services.campaign_service import CampaignService


def _request(**overrides):
    payload = dict(
        mode="existing",
        subject="Hello from Outlook",
        body="Pasted body",
        sent_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        follow_up_at=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        follow_up_action="Call",
    )
    payload.update(overrides)
    return RecordManualActivityRequest(**payload)


def test_manual_activity_updates_only_the_selected_campaign(client):
    db = SessionLocal()
    try:
        recipient = Recipient(name="Ada", email="ada-manual-activity@example.com")
        db.add(recipient)
        db.flush()
        due = datetime.now(timezone.utc) + timedelta(days=2)
        camp_a = Campaign(
            campaign_name="Inside A",
            campaign_id="CMP-MANUAL-A",
            owner="Test",
            status="active",
            subject="Live template subject",
        )
        camp_b = Campaign(
            campaign_name="Inside B",
            campaign_id="CMP-MANUAL-B",
            owner="Test",
            status="active",
        )
        db.add_all([camp_a, camp_b])
        db.flush()
        db.add(
            Template(
                campaign_id=camp_a.id,
                type="manual",
                subject="Live template subject",
                body="Do not overwrite",
            )
        )
        cr_a = CampaignRecipient(
            campaign_id=camp_a.id,
            recipient_id=recipient.id,
            status="queued",
            next_send_at=due,
        )
        cr_b = CampaignRecipient(
            campaign_id=camp_b.id,
            recipient_id=recipient.id,
            status="not_contacted",
        )
        db.add_all([cr_a, cr_b])
        db.commit()

        result = CampaignService().record_manual_activity(
            db,
            _request(campaign_id=camp_a.id, recipient_ids=[recipient.id]),
            user_id=None,
            user_name="Test",
            org_id=None,
        )

        assert result["recorded"] == 1
        db.refresh(cr_a)
        db.refresh(cr_b)
        db.refresh(camp_a)
        template = db.query(Template).filter(Template.campaign_id == camp_a.id).one()
        assert template.body == "Do not overwrite"
        assert cr_a.status == "queued"
        assert cr_a.next_send_at is not None
        assert cr_a.manual_follow_up_action == "Call"
        assert cr_b.status == "not_contacted"
        assert cr_b.manual_follow_up_at is None
        assert db.query(EmailLog).filter(EmailLog.campaign_id == camp_a.id, EmailLog.source == "manual").count() == 1
        assert db.query(EmailLog).filter(EmailLog.campaign_id == camp_b.id).count() == 0
        assert camp_a.emails_sent == 1
        assert camp_a.origin == "leadsense"
    finally:
        db.close()


def test_new_external_campaign_reuses_existing_contact(client):
    db = SessionLocal()
    try:
        recipient = Recipient(name="Grace", email="grace-manual-activity@example.com")
        db.add(recipient)
        db.commit()

        result = CampaignService().record_manual_activity(
            db,
            _request(
                mode="new",
                campaign_name="Outlook September",
                campaign_code="CMP-MANUAL-EXT",
                recipient_ids=[],
                new_contacts=[ManualContactInput(name="Someone Else", email="grace-manual-activity@example.com")],
            ),
            user_id=None,
            user_name="Test",
            org_id=None,
        )

        assert result["origin"] == "external"
        assert result["created_contacts"] == 0
        assert result["reused_contacts"] == 1
        assert db.query(Recipient).filter(Recipient.email == "grace-manual-activity@example.com").count() == 1
        campaign = db.query(Campaign).filter(Campaign.id == result["campaign_id"]).one()
        assert campaign.origin == "external"
        assert campaign.status == "active"
        cr = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.recipient_id == recipient.id)
            .one()
        )
        assert cr.status == "sent"
        assert cr.next_send_at is None
        assert db.query(Template).filter(Template.campaign_id == campaign.id).count() == 1
    finally:
        db.close()


def test_save_and_send_follow_up_queues_only_the_selected_campaign(client):
    db = SessionLocal()
    try:
        recipient = Recipient(name="Lin", email="lin-manual-followup@example.com")
        db.add(recipient)
        db.flush()
        camp_a = Campaign(
            campaign_name="Send A",
            campaign_id="CMP-MANUAL-SEND-A",
            owner="Test",
            status="active",
            origin="leadsense",
        )
        camp_b = Campaign(
            campaign_name="Send B",
            campaign_id="CMP-MANUAL-SEND-B",
            owner="Test",
            status="active",
            origin="leadsense",
        )
        db.add_all([camp_a, camp_b])
        db.flush()
        db.add(
            CampaignSequenceStage(
                campaign_id=camp_a.id,
                stage_order=1,
                delay_value=3,
                delay_unit="days",
                subject="Following up",
                body="Just checking in",
            )
        )
        db.add(CampaignRecipient(campaign_id=camp_b.id, recipient_id=recipient.id, status="not_contacted"))
        db.commit()

        when = datetime.now(timezone.utc) + timedelta(days=4)
        result = CampaignService().record_manual_activity(
            db,
            _request(
                campaign_id=camp_a.id,
                recipient_ids=[recipient.id],
                follow_up_at=when,
                send_follow_up=True,
            ),
            user_id=None,
            user_name="Test",
            org_id=None,
        )

        assert result["follow_ups_scheduled"] == 1
        cr_a = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == camp_a.id, CampaignRecipient.recipient_id == recipient.id)
            .one()
        )
        cr_b = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == camp_b.id, CampaignRecipient.recipient_id == recipient.id)
            .one()
        )
        assert cr_a.status == "sent"
        assert cr_a.next_send_at is not None
        assert cr_b.status == "not_contacted"
        assert cr_b.next_send_at is None
    finally:
        db.close()
