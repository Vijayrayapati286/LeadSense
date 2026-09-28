"""PAT whoami + org token create/revoke smoke tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "organization_tokens_test.db"
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

    # Force engine recreate against the fresh sqlite file
    import app.database.connection as conn_mod

    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()

    from app import main as main_module
    from app.database.connection import SessionLocal, init_db
    from app.middleware.auth import get_current_user
    from app.middleware.tenant import require_admin_user
    from app.models import User
    from app.services.organization_token_service import create_organization
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    init_db()

    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        org, _tok, raw = create_organization(
            db,
            name="Whoami Test Org",
            org_type="TENANT",
            mint_pat=True,
            pat_name="SmartOps UAT",
        )
        admin = User(
            name="Org Admin",
            email=f"org-admin-pat-{suffix}@example.com",
            department="Sales",
            org_id=org.org_id,
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        org_id = org.org_id
        pat = raw
        admin_id = admin.id
        org.created_by_user_id = admin_id
        db.commit()
    finally:
        db.close()

    admin_user = User(
        id=admin_id,
        name="Org Admin",
        email=f"org-admin-pat-{suffix}@example.com",
        department="Sales",
        org_id=org_id,
        role="ADMIN",
        status="ACTIVE",
    )

    async def _admin():
        return admin_user

    main_module.app.dependency_overrides[get_current_user] = _admin
    main_module.app.dependency_overrides[require_admin_user] = _admin

    with TestClient(main_module.app) as test_client:
        yield test_client, org_id, pat

    main_module.app.dependency_overrides.clear()
    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass


def test_whoami_rejects_missing_token(client):
    test_client, _org_id, _pat = client
    resp = test_client.get("/api/v1/integrations/me")
    assert resp.status_code == 401


def test_whoami_rejects_bad_token(client):
    test_client, _org_id, _pat = client
    resp = test_client.get(
        "/api/v1/integrations/me",
        headers={"Authorization": "Bearer pat_this_is_not_valid_xxxxxxxxxx"},
    )
    assert resp.status_code == 401


def test_whoami_accepts_valid_pat(client):
    test_client, org_id, pat = client
    resp = test_client.get(
        "/api/v1/integrations/me",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_id"] == org_id
    assert body["organization_name"] == "Whoami Test Org"
    assert body["type"] == "TENANT"
    assert body["token_status"] == "active"


def test_auth_me_accepts_valid_pat(client):
    test_client, org_id, pat = client
    resp = test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_id"] == org_id
    assert body["organization_name"] == "Whoami Test Org"
    assert body["type"] == "TENANT"
    assert body["token_status"] == "active"


def test_auth_me_rejects_bad_pat(client):
    test_client, _org_id, _pat = client
    resp = test_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer pat_this_is_not_valid_xxxxxxxxxx"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_organizations_list_accepts_pat(client):
    test_client, org_id, pat = client
    resp = test_client.get(
        "/api/organizations",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["organization_id"] == org_id
    assert body[0]["type"] == "TENANT"


def test_organizations_get_accepts_pat(client):
    test_client, org_id, pat = client
    resp = test_client.get(
        f"/api/organizations/{org_id}",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert resp.status_code == 200
    assert resp.json()["organization_id"] == org_id


def test_organizations_list_rejects_bad_pat(client):
    test_client, _org_id, _pat = client
    resp = test_client.get(
        "/api/organizations",
        headers={"Authorization": "Bearer pat_this_is_not_valid_xxxxxxxxxx"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_revoke_then_whoami_401(client):
    test_client, org_id, pat = client
    tokens = test_client.get(f"/api/organizations/{org_id}/tokens").json()
    assert tokens
    token_id = tokens[0]["token_id"]
    rev = test_client.post(f"/api/organizations/{org_id}/tokens/{token_id}/revoke")
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    resp = test_client.get(
        "/api/v1/integrations/me",
        headers={"Authorization": f"Bearer {pat}"},
    )
    assert resp.status_code == 401
