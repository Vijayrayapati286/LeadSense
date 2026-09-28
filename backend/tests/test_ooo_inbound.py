"""Tests for OOO classification, inbound matching, and event handlers."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "ooo_inbound_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ["USE_MOCK_SES"] = "true"
os.environ["USE_MOCK_GROQ"] = "true"
os.environ["USE_MOCK_S3"] = "true"
os.environ["USE_MOCK_MILLIONVERIFIER"] = "true"
os.environ["OOO_STOPS_FOLLOWUPS"] = "false"
os.environ["DEBUG"] = "true"

try:
    _TEST_DB.unlink(missing_ok=True)
except OSError:
    pass

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Campaign, CampaignRecipient, EmailLog, InboundEmail, Recipient, User
from app.services import event_service, inbound_email_service
from app.services.ooo_classifier import (
    CLASS_BOUNCE,
    CLASS_NORMAL_REPLY,
    CLASS_OTHER,
    CLASS_OUT_OF_OFFICE,
    classify_inbound_email,
)
from app.services.ses_service import SESService
from app.utils.helpers import utc_now
from tests.fixtures import ooo_samples


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


def _seed_sent(db, *, email=None, campaign_name=None, mime_id=None):
    suffix = uuid.uuid4().hex[:10]
    email = email or f"prospect-{suffix}@acme.com"
    campaign_name = campaign_name or f"Camp-{suffix}"
    mime_id = mime_id or f"<out-{suffix}@mail.example.com>"

    user = db.query(User).first()
    if not user:
        user = User(name="Rep", email=f"rep-{suffix}@example.com", department="Sales")
        db.add(user)
        db.flush()

    campaign = Campaign(
        campaign_name=campaign_name,
        campaign_id=f"cid-{suffix}",
        owner=user.name,
        user_id=user.id,
        status="active",
    )
    db.add(campaign)
    db.flush()

    recipient = Recipient(name="Prospect", email=email, company="Acme")
    db.add(recipient)
    db.flush()

    cr = CampaignRecipient(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status="sent",
        last_sent_at=utc_now(),
        sender_user_id=user.id,
    )
    db.add(cr)
    db.flush()

    log = EmailLog(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status="sent",
        sender_user_id=user.id,
        message_id=mime_id,
        ses_message_id=f"ses-{suffix}",
    )
    db.add(log)
    db.commit()
    return user, campaign, recipient, cr, log


def test_mock_ses_send_returns_message_ids():
    svc = SESService()
    results = [svc.send_email("a@b.com", "Hi", "<p>x</p>") for _ in range(20)]
    sent = [r for r in results if r["status"] == "sent"]
    assert sent, "expected at least one mock success"
    assert sent[0]["message_id"]
    assert sent[0]["ses_message_id"]
    assert sent[0]["message_id"].startswith("<")


def test_classify_outlook_ooo():
    raw = ooo_samples.outlook_ooo(
        from_email="prospect@acme.com",
        to_email="rep@mail.example.com",
        in_reply_to="<out-1@mail.example.com>",
    )
    parsed = inbound_email_service.parse_raw_email(raw)
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text, from_email=parsed.from_email)
    assert result.classification == CLASS_OUT_OF_OFFICE


def test_classify_ooo_without_exact_out_of_office_phrase():
    raw = ooo_samples.ooo_without_exact_phrase(
        from_email="prospect@acme.com",
        to_email="rep@mail.example.com",
        in_reply_to="<out-1@mail.example.com>",
    )
    parsed = inbound_email_service.parse_raw_email(raw)
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text, from_email=parsed.from_email)
    assert result.classification == CLASS_OUT_OF_OFFICE


def test_classify_auto_without_ooo_is_other():
    raw = ooo_samples.generic_auto_reply_no_ooo_phrase(
        from_email="system@acme.com",
        to_email="rep@mail.example.com",
        in_reply_to="<out-1@mail.example.com>",
    )
    parsed = inbound_email_service.parse_raw_email(raw)
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text, from_email=parsed.from_email)
    assert result.classification == CLASS_OTHER


def test_classify_normal_reply():
    raw = ooo_samples.normal_human_reply(
        from_email="prospect@acme.com",
        to_email="rep@mail.example.com",
        in_reply_to="<out-1@mail.example.com>",
    )
    parsed = inbound_email_service.parse_raw_email(raw)
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text, from_email=parsed.from_email)
    assert result.classification == CLASS_NORMAL_REPLY


def test_classify_bounce():
    raw = ooo_samples.bounce_dsn(to_email="rep@mail.example.com", original_recipient="prospect@acme.com")
    parsed = inbound_email_service.parse_raw_email(raw)
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text, from_email=parsed.from_email)
    assert result.classification == CLASS_BOUNCE


def test_process_outlook_ooo_marks_status(db):
    _user, campaign, recipient, cr, log = _seed_sent(db)
    raw = ooo_samples.outlook_ooo(
        from_email=recipient.email,
        to_email="rep@mail.example.com",
        in_reply_to=log.message_id,
        message_id=f"<ooo-status-{uuid.uuid4().hex[:8]}@example.com>",
    )
    result = inbound_email_service.process_raw_inbound(db, raw)
    assert result.classification == CLASS_OUT_OF_OFFICE
    assert result.matched
    assert result.campaign_id == campaign.id
    db.refresh(cr)
    assert cr.status == "out_of_office"
    assert cr.ooo_at is not None


def test_process_normal_reply_marks_replied(db):
    _user, campaign, recipient, cr, log = _seed_sent(db)
    raw = ooo_samples.normal_human_reply(
        from_email=recipient.email,
        to_email="rep@mail.example.com",
        in_reply_to=log.message_id,
    )
    # Make Message-ID unique so module-scoped DB doesn't collide
    raw = raw.replace(b"<human-1@example.com>", f"<human-{uuid.uuid4().hex[:8]}@example.com>".encode())
    result = inbound_email_service.process_raw_inbound(db, raw)
    assert result.classification == CLASS_NORMAL_REPLY
    db.refresh(cr)
    assert cr.status == "replied"


def test_duplicate_ooo_is_idempotent(db):
    _user, _campaign, recipient, cr, log = _seed_sent(db)
    mid = f"<dup-ooo-{uuid.uuid4().hex[:8]}@example.com>"
    raw = ooo_samples.outlook_ooo(
        from_email=recipient.email,
        to_email="rep@mail.example.com",
        in_reply_to=log.message_id,
        message_id=mid,
    )
    before = db.query(InboundEmail).count()
    first = inbound_email_service.process_raw_inbound(db, raw)
    second = inbound_email_service.process_raw_inbound(db, raw)
    assert first.duplicate is False
    assert second.duplicate is True
    assert db.query(InboundEmail).count() == before + 1
    db.refresh(cr)
    assert cr.status == "out_of_office"


def test_unknown_sender_does_not_crash(db):
    mid = f"<unknown-{uuid.uuid4().hex[:8]}@example.com>"
    raw = ooo_samples.outlook_ooo(
        from_email="nobody@unknown.test",
        to_email="rep@mail.example.com",
        in_reply_to="<missing@mail.example.com>",
        message_id=mid,
    )
    result = inbound_email_service.process_raw_inbound(db, raw)
    assert result.classification == CLASS_OUT_OF_OFFICE
    assert result.matched is False


def test_same_email_multiple_campaigns_uses_message_id(db):
    _u, c1, recipient, cr1, log1 = _seed_sent(db)
    suffix = uuid.uuid4().hex[:8]
    c2 = Campaign(
        campaign_name=f"B-{suffix}",
        campaign_id=f"cid-B-{suffix}",
        owner="Rep",
        user_id=_u.id,
        status="active",
    )
    db.add(c2)
    db.flush()
    cr2 = CampaignRecipient(
        campaign_id=c2.id,
        recipient_id=recipient.id,
        status="sent",
        last_sent_at=utc_now(),
        sender_user_id=_u.id,
    )
    db.add(cr2)
    mime_b = f"<b-{suffix}@mail.example.com>"
    log2 = EmailLog(
        campaign_id=c2.id,
        recipient_id=recipient.id,
        status="sent",
        message_id=mime_b,
        ses_message_id=f"ses-b-{suffix}",
    )
    db.add(log2)
    db.commit()

    raw = ooo_samples.outlook_ooo(
        from_email=recipient.email,
        to_email="rep@mail.example.com",
        in_reply_to=log2.message_id,
        message_id=f"<ooo-multi-{suffix}@example.com>",
    )
    result = inbound_email_service.process_raw_inbound(db, raw)
    assert result.campaign_id == c2.id
    db.refresh(cr1)
    db.refresh(cr2)
    assert cr2.status == "out_of_office"
    assert cr1.status == "sent"


def test_ooo_does_not_overwrite_replied(db):
    _u, campaign, recipient, cr, _log = _seed_sent(db)
    event_service.handle_reply(db, recipient.email, campaign_id=campaign.id)
    event_service.handle_out_of_office(db, recipient.email, campaign_id=campaign.id)
    db.refresh(cr)
    assert cr.status == "replied"


def test_missing_headers_still_parses():
    raw = b"Subject: hi\n\nbody only\n"
    parsed = inbound_email_service.parse_raw_email(raw)
    assert parsed.subject == "hi"
    result = classify_inbound_email(parsed.message, body_text=parsed.body_text)
    assert result.classification in {CLASS_OTHER, CLASS_NORMAL_REPLY, CLASS_OUT_OF_OFFICE, CLASS_BOUNCE}


def test_empty_and_malformed(db):
    r1 = inbound_email_service.process_raw_inbound(db, b"")
    assert r1.classification == CLASS_OTHER
    r2 = inbound_email_service.process_raw_inbound(db, ooo_samples.malformed_bytes())
    assert r2.classification in {CLASS_OTHER, CLASS_NORMAL_REPLY, CLASS_OUT_OF_OFFICE, CLASS_BOUNCE}


def test_handle_bounce_still_works(db):
    _u, campaign, recipient, cr, _log = _seed_sent(db)
    event_service.handle_bounce(db, recipient.email, bounce_type="Permanent", campaign_id=campaign.id)
    db.refresh(cr)
    assert cr.status == "bounced"
