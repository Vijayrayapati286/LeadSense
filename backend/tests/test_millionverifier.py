"""Tests for MillionVerifier pre-SES email verification gate."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Campaign, CampaignRecipient, EmailVerification, Recipient, User
from app.services.millionverifier_service import (
    MillionVerifierAuthError,
    MillionVerifierConfigError,
    MillionVerifierService,
    mask_email,
    millionverifier_diagnostic,
    validate_millionverifier_config,
)
from app.utils.helpers import utc_now


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.setenv("MILLIONVERIFIER_ENABLED", "true")
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "true")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "")
    monkeypatch.setenv("MILLIONVERIFIER_ALLOWED_RESULTS", "ok")
    monkeypatch.setenv("MILLIONVERIFIER_MAX_RETRIES", "2")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_mask_email():
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("") == "***"


def test_validate_config_mock_ok(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "true")
    get_settings.cache_clear()
    validate_millionverifier_config(get_settings())


def test_validate_config_missing_key_raises(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(MillionVerifierConfigError, match="MILLIONVERIFIER_API_KEY"):
        validate_millionverifier_config(get_settings())


def test_diagnostic_never_leaks_key(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "super-secret-key")
    get_settings.cache_clear()
    payload = millionverifier_diagnostic(check_connectivity=False)
    blob = str(payload)
    assert "super-secret-key" not in blob
    assert payload["api_key_configured"] is True
    assert payload["mock"] is False


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


def test_api_result_error_not_cached(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    get_settings.cache_clear()
    svc = MillionVerifierService()
    fake = {"email": "x@example.com", "result": "error", "resultcode": 4, "error": "greylisted"}
    db = SessionLocal()
    try:
        with patch.object(svc, "_call_api", return_value=fake):
            gate = svc.verify_email(db, "x@example.com")
        assert gate.allowed is False
        assert gate.definitive_reject is False
        assert gate.result == "error"
        assert db.query(EmailVerification).filter(EmailVerification.email == "x@example.com").count() == 0
    finally:
        db.close()


def test_auth_error_not_retried(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "bad-key")
    monkeypatch.setenv("MILLIONVERIFIER_MAX_RETRIES", "3")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    response = MagicMock()
    response.status_code = 401
    response.json.return_value = {}

    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.get.return_value = response
        client_cls.return_value = client
        with pytest.raises(MillionVerifierAuthError):
            svc._call_api("a@b.com")
        assert client.get.call_count == 1


def test_retries_on_503(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    monkeypatch.setenv("MILLIONVERIFIER_MAX_RETRIES", "2")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    fail = MagicMock()
    fail.status_code = 503
    fail.json.return_value = {}

    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {
        "email": "a@b.com",
        "result": "ok",
        "resultcode": 1,
        "quality": "good",
        "error": "",
    }

    with patch("httpx.Client") as client_cls, patch("app.services.millionverifier_service.time.sleep"):
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.get.side_effect = [fail, ok]
        client_cls.return_value = client
        data = svc._call_api("a@b.com")
        assert data["result"] == "ok"
        assert client.get.call_count == 2


def test_unexpected_result_treated_as_error(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MILLIONVERIFIER", "false")
    monkeypatch.setenv("MILLIONVERIFIER_API_KEY", "test-key")
    monkeypatch.setenv("MILLIONVERIFIER_MAX_RETRIES", "0")
    get_settings.cache_clear()
    svc = MillionVerifierService()

    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"email": "a@b.com", "result": "totally_new", "error": ""}

    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.get.return_value = ok
        client_cls.return_value = client
        db = SessionLocal()
        try:
            gate = svc.verify_email(db, "a@b.com")
            assert gate.allowed is False
            assert gate.definitive_reject is False
            assert gate.result == "error"
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
