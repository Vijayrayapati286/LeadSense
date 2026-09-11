"""Tests for MillionVerifier pre-SES email verification gate."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Campaign, CampaignRecipient, EmailVerification, Recipient, User
from app.services.millionverifier_service import MillionVerifierService
from app.utils.helpers import utc_now


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.setenv("MILLIONVERIFIER_ENABLED", "true")
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "true")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "")
    monkeypatch.setenv("MILLIONVERIFIER_ALLOWED_RESULTS", "ok")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_mock_mode_allows_and_caches():
    svc = MillionVerifierService()
    db = SessionLocal()
    try:
        gate = svc.verify_email(db, "alice@example.com")
        assert gate.allowed is True
        assert gate.result == "ok"
        db.commit()

        row = db.query(EmailVerification).filter(EmailVerification.email == "alice@example.com").one()
        assert row.result == "ok"
        assert row.source == "mock"

        gate2 = svc.verify_email(db, "Alice@Example.com")
        assert gate2.allowed is True
        assert gate2.from_cache is True
    finally:
        db.close()


def test_malformed_email_definitive_reject():
    svc = MillionVerifierService()
    db = SessionLocal()
    try:
        gate = svc.verify_email(db, "not-an-email")
        assert gate.allowed is False
        assert gate.definitive_reject is True
        assert gate.result == "invalid"
    finally:
        db.close()


def test_disabled_skips_verification(monkeypatch):
    monkeypatch.setenv("MILLIONVERIFIER_ENABLED", "false")
    get_settings.cache_clear()
    svc = MillionVerifierService()
    db = SessionLocal()
    try:
        gate = svc.verify_email(db, "anyone@example.com")
        assert gate.allowed is True
        assert gate.result == "skipped"
        assert (
            db.query(EmailVerification)
            .filter(EmailVerification.email == "anyone@example.com")
            .count()
            == 0
        )
    finally:
        db.close()


def test_api_invalid_result_blocks(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    fake = {
        "email": "bad@example.com",
        "result": "invalid",
        "resultcode": 6,
        "quality": "bad",
        "error": "",
    }
    db = SessionLocal()
    try:
        with patch.object(svc, "_call_api", return_value=fake):
            gate = svc.verify_email(db, "bad@example.com")
        assert gate.allowed is False
        assert gate.definitive_reject is True
        assert gate.result == "invalid"
        db.commit()
        row = db.query(EmailVerification).filter(EmailVerification.email == "bad@example.com").one()
        assert row.result == "invalid"
    finally:
        db.close()


def test_api_ok_allows(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    fake = {"email": "good@example.com", "result": "ok", "resultcode": 1, "quality": "good", "error": ""}
    db = SessionLocal()
    try:
        with patch.object(svc, "_call_api", return_value=fake):
            gate = svc.verify_email(db, "good@example.com")
        assert gate.allowed is True
        assert gate.definitive_reject is False
        assert gate.result == "ok"
    finally:
        db.close()


def test_api_failure_blocks_without_definitive(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    db = SessionLocal()
    try:
        with patch.object(svc, "_call_api", side_effect=RuntimeError("timeout")):
            gate = svc.verify_email(db, "retry@example.com")
        assert gate.allowed is False
        assert gate.definitive_reject is False
        assert gate.result == "error"
        assert (
            db.query(EmailVerification)
            .filter(EmailVerification.email == "retry@example.com")
            .count()
            == 0
        )
    finally:
        db.close()


def test_expired_cache_is_refreshed(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    db = SessionLocal()
    try:
        db.add(
            EmailVerification(
                email="stale@example.com",
                result="ok",
                resultcode=1,
                quality="good",
                source="millionverifier",
                verified_at=utc_now() - timedelta(days=40),
                expires_at=utc_now() - timedelta(days=10),
            )
        )
        db.commit()

        fake = {"email": "stale@example.com", "result": "invalid", "resultcode": 6, "quality": "bad", "error": ""}
        with patch.object(svc, "_call_api", return_value=fake) as mock_call:
            gate = svc.verify_email(db, "stale@example.com")
            mock_call.assert_called_once()
        assert gate.allowed is False
        assert gate.result == "invalid"
    finally:
        db.close()


def test_resolve_verification_status_helpers():
    from app.services.millionverifier_service import resolve_verification_status

    assert resolve_verification_status(
        email="a@b.com", suppression_reason=None, cache_row=None
    ) == ("unchecked", None)

    assert resolve_verification_status(
        email="a@b.com",
        suppression_reason="email_verification_failed",
        cache_row=None,
    )[0] == "failed"


def test_apply_rejection_suppresses_recipient():
    svc = MillionVerifierService()
    db = SessionLocal()
    try:
        user = User(name="Rep", email="rep-mv-test@example.com")
        db.add(user)
        db.flush()
        campaign = Campaign(
            campaign_name="MV Test",
            campaign_id="mv-test-001",
            owner="Rep",
            user_id=user.id,
            status="active",
        )
        db.add(campaign)
        db.flush()
        recipient = Recipient(name="Bad Lead", email="reject@example.com", company="Acme")
        db.add(recipient)
        db.flush()
        cr = CampaignRecipient(campaign_id=campaign.id, recipient_id=recipient.id, status="queued")
        db.add(cr)
        db.flush()

        from app.services.millionverifier_service import VerificationGateResult

        gate = VerificationGateResult(
            allowed=False,
            definitive_reject=True,
            result="invalid",
            detail="MillionVerifier result: invalid",
        )
        svc.apply_rejection(
            db,
            recipient=recipient,
            campaign_id=campaign.id,
            campaign_recipient=cr,
            gate=gate,
            sender_user_id=user.id,
        )
        db.commit()

        db.refresh(recipient)
        db.refresh(cr)
        assert recipient.is_suppressed is True
        assert recipient.suppression_reason == "email_verification_failed"
        assert cr.status == "invalid_email"
        assert cr.next_send_at is None
    finally:
        db.close()
