"""PAT-scoped leads APIs for SmartOps sync."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "leads_api_test.db"
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
    from app.database.connection import SessionLocal, init_db
    from app.services.organization_token_service import create_organization
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    init_db()

    db = SessionLocal()
    try:
        org, _tok, raw = create_organization(
            db,
            name=f"Leads Org {uuid.uuid4().hex[:6]}",
            org_type="TENANT",
            mint_pat=True,
            pat_name="SmartOps",
        )
        org_id = org.org_id
        pat = raw
    finally:
        db.close()

    with TestClient(main_module.app) as test_client:
        yield test_client, org_id, pat

    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass


def _auth(pat: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {pat}"}


def test_leads_require_pat(client):
    test_client, _org_id, _pat = client
    assert test_client.get("/api/leads").status_code == 401
    assert test_client.get("/api/leads", headers=_auth("pat_bad_token_xxxxxxxxxxxx")).status_code == 401


def test_leads_crud_and_org_path(client):
    test_client, org_id, pat = client
    created = test_client.post(
        "/api/leads",
        headers=_auth(pat),
        json={"title": "Acme follow-up", "status": "open", "company": "Acme", "source": "smartops"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["organization_id"] == org_id
    assert body["title"] == "Acme follow-up"
    assert body["id"].startswith("lead_")
    lead_id = body["id"]

    listed = test_client.get("/api/leads", headers=_auth(pat))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == lead_id

    org_listed = test_client.get(f"/api/organizations/{org_id}/leads", headers=_auth(pat))
    assert org_listed.status_code == 200
    assert org_listed.json()["total"] == 1

    fetched = test_client.get(f"/api/leads/{lead_id}", headers=_auth(pat))
    assert fetched.status_code == 200
    assert fetched.json()["company"] == "Acme"

    patched = test_client.patch(
        f"/api/leads/{lead_id}",
        headers=_auth(pat),
        json={"status": "won", "notes": "Closed in SmartOps"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "won"
    assert patched.json()["notes"] == "Closed in SmartOps"

    other = test_client.get(
        f"/api/organizations/org_does_not_match/leads",
        headers=_auth(pat),
    )
    assert other.status_code == 404
