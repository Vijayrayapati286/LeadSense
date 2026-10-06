"""End-to-end path: SmartOps sync → stored content → campaign Offering Email templates.

Path under test:
  1) PAT POST /api/offerings  (SmartOps sync shape)
  2) Content + docs stored on offerings / offering_documents
  3) JWT GET /api/templates/placeholder-templates?offering_id=
     → Introduction Outreach / Product Demo Invite / Follow-up Email
     grounded in that offering's content
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "offering_campaign_email_path_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ["USE_MOCK_SES"] = "true"
os.environ["USE_MOCK_GROQ"] = "true"
os.environ["USE_MOCK_S3"] = "true"
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
    from app.models import User
    from app.services.auth_service import AuthService
    from app.services.organization_token_service import create_organization
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    init_db()

    db = SessionLocal()
    try:
        org, _tok, pat = create_organization(
            db,
            name=f"Path Org {uuid.uuid4().hex[:6]}",
            org_type="TENANT",
            mint_pat=True,
            pat_name="SmartOps",
        )
        email = f"advisor-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            name="Path Tester",
            email=email,
            department="Sales",
            password_hash=AuthService.hash_password("TestPass123!"),
            org_id=org.org_id,
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(user)
        db.flush()
        org.owner_user_id = user.id
        db.commit()
        org_id = org.org_id
        user_id = user.id
        user_email = user.email
    finally:
        db.close()

    with TestClient(main_module.app) as test_client:
        yield test_client, org_id, pat, user_email, user_id

    if hasattr(conn_mod.engine, "dispose"):
        conn_mod.engine.dispose()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except OSError:
        pass


def _pat(pat: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {pat}"}


def _jwt(client, email: str) -> dict[str, str]:
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _smartops_payload(org_id: str) -> dict:
    return {
        "organization_id": org_id,
        "smartops_offering_id": "off_01PATHTESTWEALTH0000000001",
        "name": "SmartOps Wealth Advisory Pack",
        "description": "HNI second-opinion and fiduciary discovery pack.",
        "doc_count": 2,
        "docs": [
            {
                "doc_id": "odoc_PATH_WEALTH_PITCH_001",
                "file_name": "wealth_advisory_pitch.pdf",
                "file_format": "pdf",
                "s3_key": "offerings/path/wealth_advisory_pitch.pdf",
                "download_url": "https://example.com/presigned/wealth_advisory_pitch.pdf",
                "content": (
                    "SmartOps Wealth helps advisors coach live calls and "
                    "position a second opinion without trashing the incumbent. "
                    "Advisors use live coaching prompts during discovery to surface "
                    "fee transparency and proactive planning gaps before the pitch."
                ),
                "created_at": "2026-10-06T10:00:00Z",
            },
            {
                "doc_id": "odoc_PATH_WEALTH_COMP_001",
                "file_name": "WM13_Competitive_Wirehouse_vs_RIA.pdf",
                "file_format": "pdf",
                "s3_key": "offerings/path/WM13.pdf",
                "download_url": "https://example.com/presigned/WM13.pdf",
                "content": (
                    "Ask about fiduciary status, total fees, and proactivity. "
                    "Compare wirehouse vs RIA on conflicts, product shelf, and "
                    "who owns the advice relationship after the review."
                ),
                "created_at": "2026-10-06T10:01:00Z",
            },
        ],
        "created_at": "2026-10-06T09:00:00Z",
    }


def test_whole_path_smartops_sync_to_campaign_offering_email(client):
    test_client, org_id, pat, user_email, _user_id = client

    # 1) SmartOps sync
    sync = test_client.post(
        "/api/offerings",
        headers=_pat(pat),
        json=_smartops_payload(org_id),
    )
    assert sync.status_code == 201, sync.text
    body = sync.json()
    assert body["name"] == "SmartOps Wealth Advisory Pack"
    assert body["doc_count"] == 2
    content = body.get("content") or ""
    assert "HNI second-opinion" in content
    assert "second opinion without trashing" in content
    assert "fiduciary status" in content
    ls_public_id = body["offering_id"]
    assert ls_public_id.startswith("ls_off_")

    # 2) Resolve numeric id used by campaign UI
    from app.database.connection import SessionLocal
    from app.offerings.models import OfferingDocumentRow, OfferingRow

    db = SessionLocal()
    try:
        row = db.query(OfferingRow).filter(OfferingRow.offering_id == ls_public_id).one()
        offering_pk = row.id
        docs = (
            db.query(OfferingDocumentRow)
            .filter(OfferingDocumentRow.offering_id == ls_public_id)
            .all()
        )
        assert len(docs) == 2
        assert row.content == content
        assert all(d.download_url and d.download_url.startswith("https://") for d in docs)
        assert row.file_url and row.file_url.startswith("https://")
    finally:
        db.close()

    # 3) Campaign Offering Email templates for that offering id
    headers = _jwt(test_client, user_email)
    templates = test_client.get(
        f"/api/templates/placeholder-templates?offering_id={offering_pk}",
        headers=headers,
    )
    assert templates.status_code == 200, templates.text
    items = templates.json()
    assert len(items) == 3
    by_name = {t["name"]: t for t in items}
    assert "Introduction Outreach" in by_name
    assert "Product Demo Invite" in by_name
    assert "Follow-up Email" in by_name

    for name, tpl in by_name.items():
        assert tpl.get("source") == "offering", name
        assert tpl.get("offering_id") == offering_pk, name
        blob = (tpl.get("subject") or "") + (tpl.get("body") or "")
        assert "SmartOps" in blob, f"{name} missing offering signal: {blob[:200]}"
        # Content from synced docs / description must appear in each type
        assert (
            "HNI second-opinion" in blob
            or "second opinion without trashing" in blob
            or "fiduciary" in blob.lower()
            or "SmartOps Wealth" in blob
            or "wirehouse" in blob.lower()
            or "fee" in blob.lower()
            or "advisor" in blob.lower()
        ), f"{name} missing offering content: {blob[:200]}"

    # Selecting each type returns distinct subjects (campaign picker behavior)
    subjects = {t["name"]: t["subject"] for t in items}
    assert subjects["Introduction Outreach"] != subjects["Product Demo Invite"]
    assert subjects["Follow-up Email"] != subjects["Introduction Outreach"]

    # AI-by-type: bodies must not be identical blurbs
    bodies = [by_name[n]["body"] for n in (
        "Introduction Outreach", "Product Demo Invite", "Follow-up Email"
    )]
    assert len(set(bodies)) >= 2
