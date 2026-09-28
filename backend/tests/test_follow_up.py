"""Follow-up scheduling, mark-replied, and multi-campaign isolation tests."""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "follow_up_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ["USE_MOCK_SES"] = "true"
os.environ["USE_MOCK_GROQ"] = "true"
os.environ["USE_MOCK_S3"] = "true"
os.environ["USE_MOCK_MILLIONVERIFIER"] = "true"
os.environ["DEBUG"] = "true"

try:
    _TEST_DB.unlink(missing_ok=True)
except OSError:
    pass

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Campaign, CampaignRecipient, CampaignSequenceStage, Recipient, User
from app.services.campaign_service import CampaignService, derive_follow_up_state
from app.services import event_service
from app.utils.helpers import utc_now


@pytest.fixture(scope="module")
def db():
    get_settings.cache_clear()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _user(db) -> User:
    user = db.query(User).first()
    if user:
        return user
    user = User(name="Rep", email=f"rep-{_suffix()}@example.com", department="Sales")
    db.add(user)
    db.flush()
    return user


def _campaign(db, user: User, name: str | None = None) -> Campaign:
    suffix = _suffix()
    campaign = Campaign(
        campaign_name=name or f"Camp-{suffix}",
        campaign_id=f"cid-{suffix}",
        owner=user.name,
        user_id=user.id,
        status="active",
    )
    db.add(campaign)
    db.flush()
    return campaign


def _recipient(db, email: str | None = None) -> Recipient:
    suffix = _suffix()
    recipient = Recipient(
        name="Prospect",
        email=email or f"prospect-{suffix}@acme.com",
        company="Acme",
    )
    db.add(recipient)
    db.flush()
    return recipient


def _link(
    db,
    campaign: Campaign,
    recipient: Recipient,
    *,
    status: str = "sent",
    current_stage: int = 0,
    next_send_at=None,
) -> CampaignRecipient:
    cr = CampaignRecipient(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status=status,
        current_stage=current_stage,
        next_send_at=next_send_at,
        last_sent_at=utc_now() if status == "sent" else None,
    )
    db.add(cr)
    db.flush()
    return cr


def _stage(db, campaign: Campaign, order: int = 1) -> CampaignSequenceStage:
    stage = CampaignSequenceStage(
        campaign_id=campaign.id,
        stage_order=order,
        delay_value=3,
        delay_unit="days",
        subject=f"Follow-up {order}",
        body="Just checking in, {{name}}.",
    )
    db.add(stage)
    db.flush()
    return stage


@pytest.fixture()
def service() -> CampaignService:
    return CampaignService()


def test_schedule_remaining_excludes_replied(db, service):
    """Test 1 — 5 replied / 95 remaining → schedule only non-replied."""
    user = _user(db)
    campaign = _campaign(db, user)
    _stage(db, campaign)

    recipients = [_recipient(db) for _ in range(10)]
    for i, r in enumerate(recipients):
        status = "replied" if i < 2 else "sent"
        _link(db, campaign, r, status=status)
    db.commit()

    when = utc_now() + timedelta(days=2)
    result = service.schedule_followups(
        db, campaign.id, when, all_non_replied=True
    )
    assert result["scheduled"] == 8
    assert result["skipped"] == 0

    rows = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign.id)
        .all()
    )
    replied = [cr for cr in rows if cr.status == "replied"]
    scheduled = [cr for cr in rows if cr.next_send_at is not None]
    assert len(replied) == 2
    assert all(cr.next_send_at is None for cr in replied)
    assert len(scheduled) == 8


def test_same_email_multi_campaign_isolation(db, service):
    """Test 2 — mark replied on Campaign A must not change B or C."""
    user = _user(db)
    email = f"john-{_suffix()}@example.com"
    recipient = _recipient(db, email=email)

    camp_a = _campaign(db, user, "Campaign A")
    camp_b = _campaign(db, user, "Campaign B")
    camp_c = _campaign(db, user, "Campaign C")
    _stage(db, camp_a)
    _stage(db, camp_c)

    cr_a = _link(db, camp_a, recipient, status="sent")
    cr_b = _link(db, camp_b, recipient, status="sent")
    when = utc_now() + timedelta(days=1)
    cr_c = _link(db, camp_c, recipient, status="sent", next_send_at=when)
    db.commit()

    result = service.mark_recipients_replied(db, camp_a.id, [recipient.id])
    assert result["updated"] == 1

    db.refresh(cr_a)
    db.refresh(cr_b)
    db.refresh(cr_c)

    assert cr_a.status == "replied"
    assert cr_a.replied_at is not None
    assert cr_a.next_send_at is None

    assert cr_b.status == "sent"
    assert cr_b.replied_at is None

    assert cr_c.status == "sent"
    assert cr_c.next_send_at is not None
    state, _ = derive_follow_up_state(cr_c)
    assert state == "scheduled"


def test_reply_after_schedule_clears_next_send(db, service):
    """Test 3 — reply after schedule cancels pending follow-up."""
    user = _user(db)
    campaign = _campaign(db, user)
    _stage(db, campaign)
    recipient = _recipient(db)
    when = utc_now() + timedelta(hours=6)
    cr = _link(db, campaign, recipient, status="sent", next_send_at=when)
    db.commit()

    service.mark_recipients_replied(db, campaign.id, [recipient.id])
    db.refresh(cr)
    assert cr.status == "replied"
    assert cr.next_send_at is None
    state, _ = derive_follow_up_state(cr)
    assert state == "cancelled"


def test_inbound_reply_scoped_to_matched_campaign(db):
    """Inbound reply with campaign_id updates only that campaign relationship."""
    user = _user(db)
    email = f"multi-{_suffix()}@example.com"
    recipient = _recipient(db, email=email)
    camp_a = _campaign(db, user, "A")
    camp_b = _campaign(db, user, "B")
    cr_a = _link(db, camp_a, recipient, status="sent", next_send_at=utc_now() + timedelta(days=1))
    cr_b = _link(db, camp_b, recipient, status="sent", next_send_at=utc_now() + timedelta(days=2))
    db.commit()

    event_service.handle_reply(db, email, campaign_id=camp_a.id)

    db.refresh(cr_a)
    db.refresh(cr_b)
    assert cr_a.status == "replied"
    assert cr_a.next_send_at is None
    assert cr_b.status == "sent"
    assert cr_b.next_send_at is not None


def test_ten_campaigns_independent_status(db, service):
    """Test 4 — same recipient across 10 campaigns keeps independent status."""
    user = _user(db)
    recipient = _recipient(db)
    campaigns = [_campaign(db, user, f"Camp-{i}") for i in range(10)]
    links = []
    for i, camp in enumerate(campaigns):
        status = "replied" if i == 0 else "sent"
        next_at = utc_now() + timedelta(days=1) if i == 2 else None
        links.append(_link(db, camp, recipient, status=status, next_send_at=next_at))
    db.commit()

    service.mark_recipients_replied(db, campaigns[5].id, [recipient.id])

    for i, cr in enumerate(links):
        db.refresh(cr)
        if i == 0:
            assert cr.status == "replied"
        elif i == 5:
            assert cr.status == "replied"
            assert cr.next_send_at is None
        elif i == 2:
            assert cr.status == "sent"
            assert cr.next_send_at is not None
        else:
            assert cr.status == "sent"
            assert cr.replied_at is None


def test_cancel_followup_clears_schedule_only(db, service):
    user = _user(db)
    campaign = _campaign(db, user)
    _stage(db, campaign)
    recipient = _recipient(db)
    when = utc_now() + timedelta(days=3)
    cr = _link(db, campaign, recipient, status="sent", next_send_at=when)
    db.commit()

    result = service.cancel_followups(db, campaign.id, recipient_ids=[recipient.id])
    assert result["cancelled"] == 1
    db.refresh(cr)
    assert cr.status == "sent"
    assert cr.next_send_at is None
    state, label = derive_follow_up_state(cr)
    assert state == "none"
    assert label == "No follow-up"


def test_cancel_skips_replied_and_unscheduled(db, service):
    user = _user(db)
    campaign = _campaign(db, user)
    r1 = _recipient(db)
    r2 = _recipient(db)
    _link(db, campaign, r1, status="replied")
    _link(db, campaign, r2, status="sent", next_send_at=None)
    db.commit()

    result = service.cancel_followups(
        db, campaign.id, recipient_ids=[r1.id, r2.id]
    )
    assert result["cancelled"] == 0
    assert result["skipped"] == 2
