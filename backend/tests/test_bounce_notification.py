"""Bounce notices go to the user who sent the message, looked up by SES id."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "bounce_notification_test.db"
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

import pytest

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Campaign, CampaignRecipient, EmailLog, Recipient, User, UserNotification
from app.routers.webhooks import _process_bounce
from app.services.bounce_notification_service import notify_sender_of_bounce


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


def _seed_send(db, *, name, email, prospect, ses_id):
    user = User(name=name, email=email, department="Sales", org_id=None)
    db.add(user)
    db.flush()
    suffix = uuid.uuid4().hex[:8]
    campaign = Campaign(
        campaign_name=f"{name} campaign",
        campaign_id=f"cid-{suffix}",
        owner=name,
        user_id=user.id,
        status="active",
    )
    db.add(campaign)
    db.flush()
    recipient = Recipient(name="Prospect", email=prospect, company="Acme")
    db.add(recipient)
    db.flush()
    cr = CampaignRecipient(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status="sent",
        sender_user_id=user.id,
    )
    db.add(cr)
    log = EmailLog(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status="sent",
        sender_user_id=user.id,
        ses_message_id=ses_id,
    )
    db.add(log)
    db.commit()
    return user, campaign, recipient, log


def test_bounce_notifies_only_the_sender(db, monkeypatch):
    sent = []

    def _fake_send(**kwargs):
        sent.append(kwargs["to_email"])
        return {"status": "sent"}

    monkeypatch.setattr("app.services.bounce_notification_service._ses.send_email", _fake_send)
    suffix = uuid.uuid4().hex[:8]
    vijay, _, _, vijay_log = _seed_send(
        db,
        name="Vijay",
        email=f"vijay-{suffix}@example.com",
        prospect=f"prospect-v-{suffix}@acme.com",
        ses_id=f"ses-vijay-{suffix}",
    )
    rahul, _, _, _ = _seed_send(
        db,
        name="Rahul",
        email=f"rahul-{suffix}@example.com",
        prospect=f"prospect-r-{suffix}@acme.com",
        ses_id=f"ses-rahul-{suffix}",
    )

    notify_sender_of_bounce(
        db,
        ses_message_id=vijay_log.ses_message_id,
        recipient_email=f"prospect-v-{suffix}@acme.com",
        bounce_type="Permanent",
    )

    assert sent == [vijay.email]
    vijay_notes = db.query(UserNotification).filter(UserNotification.user_id == vijay.id).all()
    rahul_notes = db.query(UserNotification).filter(UserNotification.user_id == rahul.id).all()
    assert len(vijay_notes) == 1
    assert vijay_notes[0].emailed_at is not None
    assert rahul_notes == []


def test_duplicate_bounce_does_not_email_twice(db, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.bounce_notification_service._ses.send_email",
        lambda **kwargs: sent.append(kwargs["to_email"]) or {"status": "sent"},
    )
    suffix = uuid.uuid4().hex[:8]
    user, _, _, log = _seed_send(
        db,
        name="Anand",
        email=f"anand-{suffix}@example.com",
        prospect=f"prospect-a-{suffix}@acme.com",
        ses_id=f"ses-anand-{suffix}",
    )
    for _ in range(2):
        notify_sender_of_bounce(
            db,
            ses_message_id=log.ses_message_id,
            recipient_email=f"prospect-a-{suffix}@acme.com",
            bounce_type="Permanent",
        )
    assert sent == [user.email]
    assert db.query(UserNotification).filter(UserNotification.user_id == user.id).count() == 1


def test_webhook_bounce_still_updates_status_and_notifies_sender(db, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.bounce_notification_service._ses.send_email",
        lambda **kwargs: sent.append(kwargs["to_email"]) or {"status": "sent"},
    )
    suffix = uuid.uuid4().hex[:8]
    user, campaign, recipient, log = _seed_send(
        db,
        name="Vijay",
        email=f"vijay-hook-{suffix}@example.com",
        prospect=f"hook-{suffix}@acme.com",
        ses_id=f"ses-hook-{suffix}",
    )
    _process_bounce(
        db,
        {
            "notificationType": "Bounce",
            "mail": {"messageId": log.ses_message_id},
            "bounce": {
                "bounceType": "Permanent",
                "bouncedRecipients": [{"emailAddress": recipient.email, "diagnosticCode": "550 5.1.1 user unknown"}],
            },
        },
    )
    db.refresh(recipient)
    from app.models import CampaignRecipient

    cr = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.recipient_id == recipient.id)
        .one()
    )
    assert cr.status == "bounced"
    assert sent == [user.email]


def test_notification_api_is_private_to_the_sender(db, monkeypatch):
    """Smoke the bell's API: the sender sees the bounce, the other user does not."""
    monkeypatch.setattr(
        "app.services.bounce_notification_service._ses.send_email",
        lambda **kwargs: {"status": "sent", "to": kwargs["to_email"]},
    )
    suffix = uuid.uuid4().hex[:8]
    prospect = f"smoke-{suffix}@acme.com"
    vijay, _, _, log = _seed_send(
        db,
        name="Vijay",
        email=f"vijay-api-{suffix}@example.com",
        prospect=prospect,
        ses_id=f"ses-api-{suffix}",
    )
    rahul, _, _, _ = _seed_send(
        db,
        name="Rahul",
        email=f"rahul-api-{suffix}@example.com",
        prospect=f"other-{suffix}@acme.com",
        ses_id=f"ses-other-{suffix}",
    )
    notify_sender_of_bounce(
        db,
        ses_message_id=log.ses_message_id,
        recipient_email=prospect,
        bounce_type="Permanent",
        detail="550 5.1.1 user unknown",
    )

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.auth_service import AuthService

    auth = AuthService()
    vijay_headers = {"Authorization": f"Bearer {auth._create_jwt(vijay)}"}
    rahul_headers = {"Authorization": f"Bearer {auth._create_jwt(rahul)}"}

    with TestClient(app) as client:
        missing = client.get("/api/notifications")
        assert missing.status_code == 401

        vijay_list = client.get("/api/notifications", headers=vijay_headers)
        assert vijay_list.status_code == 200
        payload = vijay_list.json()
        assert payload["unread_count"] >= 1
        match = next(item for item in payload["items"] if item["recipient_email"] == prospect)
        assert match["read"] is False
        assert "bounced" in match["body"].lower()

        rahul_list = client.get("/api/notifications", headers=rahul_headers)
        assert rahul_list.status_code == 200
        assert all(item["recipient_email"] != prospect for item in rahul_list.json()["items"])

        hidden = client.post(f"/api/notifications/{match['id']}/read", headers=rahul_headers)
        assert hidden.status_code == 404

        marked = client.post(f"/api/notifications/{match['id']}/read", headers=vijay_headers)
        assert marked.status_code == 200
        assert marked.json()["read"] is True

        cleared = client.post("/api/notifications/read-all", headers=vijay_headers)
        assert cleared.status_code == 200
        assert cleared.json()["unread_count"] == 0
