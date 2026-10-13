"""Inbox-placement headers and public unsubscribe."""

from __future__ import annotations

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.models import Recipient, SuppressionEntry
from app.services.ses_service import SESService
from app.utils.unsubscribe import list_unsubscribe_value, unsubscribe_token, valid_unsubscribe_token


def _decoded_bodies(raw) -> str:
    chunks = []
    for part in raw.walk():
        if part.get_content_type() in ("text/html", "text/plain"):
            payload = part.get_payload(decode=True) or b""
            chunks.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def setup_module():
    get_settings.cache_clear()
    init_db()


def test_unsubscribe_token_roundtrip():
    email = "lead@example.com"
    token = unsubscribe_token(email, secret="test-secret")
    assert valid_unsubscribe_token(email, token, secret="test-secret")
    assert not valid_unsubscribe_token(email, "nope", secret="test-secret")
    assert not valid_unsubscribe_token("other@example.com", token, secret="test-secret")


def test_list_unsubscribe_header_has_mailto_and_https():
    value = list_unsubscribe_value("lead@example.com", "ada@outreach.feuji.com")
    assert "mailto:ada@outreach.feuji.com" in value
    assert "/api/public/unsubscribe" in value
    assert "token=" in value


def _aligned_svc(monkeypatch) -> SESService:
    monkeypatch.setenv("SES_USE_SENDING_DOMAIN_REPLY_TO", "true")
    monkeypatch.setenv("AWS_SES_SENDING_DOMAIN", "outreach.feuji.com")
    get_settings.cache_clear()
    svc = SESService()
    svc.settings = get_settings()
    return svc


def test_raw_message_aligns_reply_to_and_adds_unsub(monkeypatch):
    svc = _aligned_svc(monkeypatch)
    source = svc._build_source("Ada Lovelace", "ada@feuji.com")
    reply = svc._resolve_reply_to("ada@feuji.com", source)
    assert "outreach.feuji.com" in (reply or "")
    raw = svc._build_raw_message(
        source, "lead@example.com", "Hi", "<html><body><p>Hi</p></body></html>", "Hi", reply
    )
    assert raw["List-Unsubscribe"]
    assert raw["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "lead%40example.com" in raw["List-Unsubscribe"]
    assert "campaigns.outreach.feuji.com" in (raw["List-Id"] or "")
    bodies = _decoded_bodies(raw)
    assert "unsubscribe here" in bodies.lower()
    assert bodies.lower().rfind("unsubscribe here") < bodies.lower().rfind("</body>")


def test_raw_message_headers_stable_across_body_styles(monkeypatch):
    """Junk-folder fix must hold for short, long, HTML, and inline-image bodies."""
    svc = _aligned_svc(monkeypatch)
    source = svc._build_source("Ada Lovelace", "ada@feuji.com")
    reply = svc._resolve_reply_to("ada@feuji.com", source)
    tiny_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    bodies = [
        ("plain", "<p>Hi {{Name}}</p>", "Hi {{Name}}"),
        (
            "long-html",
            "<html><body><p>Hello {{Name}} at {{Company}},</p>"
            "<p>We help healthcare RCM teams cut denials and prior-auth backlog.</p>"
            "<p>Would you be open to a 15-minute intro?</p></body></html>",
            "Hello {{Name}} at {{Company}}",
        ),
        (
            "inline-image",
            f'<p>Logo</p><img src="data:image/png;base64,{tiny_png}" alt="logo">',
            "Logo",
        ),
        ("empty-text", "<div><strong>Offer</strong></div>", None),
    ]
    for _label, html, text in bodies:
        raw = svc._build_raw_message(source, "lead@example.com", "Intro — {{Company}}", html, text, reply)
        payload = raw.as_string()
        bodies = _decoded_bodies(raw)
        assert "@outreach.feuji.com" in raw["From"]
        assert raw["Reply-To"] == reply
        assert raw["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert raw["List-Id"]
        assert "/api/public/unsubscribe" in payload
        assert "unsubscribe here" in bodies.lower()
        if _label == "inline-image":
            assert "Content-ID:" in payload


def test_public_unsubscribe_suppresses():
    from app.routers.unsubscribe import _unsubscribe

    db = SessionLocal()
    try:
        email = "optout@example.com"
        db.add(Recipient(name="Opt Out", email=email, company="Acme"))
        db.commit()
        token = unsubscribe_token(email)
        result = _unsubscribe(email, token, db)
        assert result["status"] == "unsubscribed"
        row = db.query(Recipient).filter(Recipient.email == email).one()
        assert row.is_suppressed is True
        assert row.suppression_reason == "unsubscribe"
        assert db.query(SuppressionEntry).filter(SuppressionEntry.email == email).count() == 1
    finally:
        db.close()


def test_invite_mail_skips_unsubscribe_headers(monkeypatch):
    svc = _aligned_svc(monkeypatch)
    source = svc._build_source("LeadSense", "ada@feuji.com")
    raw = svc._build_raw_message(
        source,
        "new.user@example.com",
        "You're invited",
        "<p>Accept invite</p>",
        "Accept invite",
        None,
        add_unsubscribe=False,
    )
    assert raw["List-Unsubscribe"] is None
    assert raw["List-Id"] is None
    assert "unsubscribe here" not in _decoded_bodies(raw).lower()
