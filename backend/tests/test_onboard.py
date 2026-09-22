"""Provider seed + tenant onboard with email verify and owner invites."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

_TEST_DB = Path(__file__).resolve().parent / "onboard_api_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ.setdefault("USE_MOCK_SES", "true")
os.environ.setdefault("USE_MOCK_GROQ", "true")
os.environ.setdefault("USE_MOCK_S3", "true")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")


@pytest.fixture()
def client(monkeypatch):
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass

    import app.services.scheduler_service as scheduler_service

    monkeypatch.setattr(scheduler_service, "start_scheduler", lambda: None)
    monkeypatch.setattr(scheduler_service, "stop_scheduler", lambda: None)

    from app.config import get_settings

    get_settings.cache_clear()

    import app.database.connection as conn_mod

    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()

    from app import main as main_module

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    with TestClient(main_module.app) as test_client:
        yield test_client

    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _token_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def test_provider_seed_login(client):
    headers = _login(client, "provider.admin@feuji.com", "Provider@123")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "provider.admin@feuji.com"
    assert body["role"] == "ADMIN"
    assert body["org_type"] == "PROVIDER"
    assert body["org_name"] == "Feuji"

    user_headers = _login(client, "provider.user@feuji.com", "ProviderUser@123")
    user_me = client.get("/api/auth/me", headers=user_headers).json()
    assert user_me["role"] == "USER"
    assert user_me["org_type"] == "PROVIDER"


def test_tenant_onboard_verify_password_and_invite(client):
    provider = _login(client, "provider.admin@feuji.com", "Provider@123")
    owner_email = f"owner-{uuid4().hex[:8]}@example.com"
    member_email = f"member-{uuid4().hex[:8]}@example.com"

    created = client.post(
        "/api/organizations",
        headers=provider,
        json={
            "name": "Acme Tenant",
            "owner_name": "Casey Owner",
            "owner_email": owner_email,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["name"] == "Acme Tenant"
    assert payload["client_name"] == "Casey Owner"
    assert payload["type"] == "TENANT"
    assert payload["owner_email"] == owner_email
    assert payload["owner_verify_url"]
    assert payload["token"]["token"].startswith("pat_")

    verify_token = _token_from_url(payload["owner_verify_url"])
    preview = client.get(f"/api/onboard/verify/{verify_token}")
    assert preview.status_code == 200
    assert preview.json()["email"] == owner_email
    assert preview.json()["client_name"] == "Casey Owner"

    blocked = client.post(
        "/api/auth/login",
        json={"email": owner_email, "password": "OwnerPass1"},
    )
    assert blocked.status_code == 401

    complete = client.post(
        f"/api/onboard/verify/{verify_token}",
        json={"password": "OwnerPass1", "name": "Casey Owner"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["user"]["status"] == "ACTIVE"

    owner = _login(client, owner_email, "OwnerPass1")
    me = client.get("/api/auth/me", headers=owner).json()
    assert me["org_type"] == "TENANT"
    assert me["role"] == "ADMIN"
    assert me["client_name"] == "Casey Owner"

    forbidden = client.post(
        "/api/organizations",
        headers=owner,
        json={
            "name": "Should Fail",
            "client_name": "Nope",
            "owner_name": "Nope",
            "owner_email": "nope@example.com",
        },
    )
    assert forbidden.status_code == 403

    invited = client.post(
        "/api/invites",
        headers=owner,
        json={"email": member_email, "role": "USER"},
    )
    assert invited.status_code == 201, invited.text

    from app.database.connection import SessionLocal
    from app.models import Invite

    db = SessionLocal()
    try:
        invite = db.query(Invite).filter(Invite.email == member_email).first()
        assert invite is not None
        invite_token = invite.invite_token
    finally:
        db.close()

    invite_preview = client.get(f"/api/onboard/invite/{invite_token}")
    assert invite_preview.status_code == 200
    assert invite_preview.json()["email"] == member_email

    accepted = client.post(
        f"/api/onboard/invite/{invite_token}",
        json={"name": "Morgan Member", "password": "MemberPass1"},
    )
    assert accepted.status_code == 200, accepted.text

    member = _login(client, member_email, "MemberPass1")
    member_me = client.get("/api/auth/me", headers=member).json()
    assert member_me["role"] == "USER"
    assert member_me["org_id"] == me["org_id"]
