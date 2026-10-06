"""PAT-scoped SmartOps offering sync on /api/offerings."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_TEST_DB = Path(__file__).resolve().parent / "offering_smartops_test.db"
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
            name=f"Offer Org {uuid.uuid4().hex[:6]}",
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


def _docs(*names: tuple[str, str, str]) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "offering_id": "off_01KYVG27FVHC98JYHWN2FRCBPH",
            "file_name": file_name,
            "file_format": file_format,
            "s3_key": f"offerings/ten_xxx/{file_name}",
            "content": f"Extracted text from {file_name}",
            "created_at": "2026-09-25T15:30:00Z",
        }
        for doc_id, file_name, file_format in names
    ]


def _payload(org_id: str, **overrides) -> dict:
    docs = _docs(
        ("odoc_01M3CP0TVBW0X7NE8THKGNHMCV", "pitch_deck.pdf", "pdf"),
        ("odoc_01M3CP0V39Y68BBAE6RXQBSN5X", "pricing_guide.docx", "docx"),
    )
    body = {
        "organization_id": org_id,
        "name": "Enterprise Pitch Pack",
        "description": "Q4 enterprise solution overview with pricing",
        "doc_count": 2,
        "docs": docs,
        "smartops_offering_id": "off_01KYVG27FVHC98JYHWN2FRCBPH",
        "created_at": "2026-09-25T10:00:00Z",
    }
    body.update(overrides)
    return body


def test_offerings_require_auth(client):
    test_client, _org_id, _pat = client
    assert test_client.get("/api/offerings").status_code == 401
    assert test_client.post("/api/offerings", json={"name": "X"}).status_code == 401


def test_smartops_create_idempotent_update_and_list(client):
    test_client, org_id, pat = client
    first = test_client.post("/api/offerings", headers=_auth(pat), json=_payload(org_id))
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["organization_id"] == org_id
    assert body["name"] == "Enterprise Pitch Pack"
    assert body["status"] == "active"
    assert body["doc_count"] == 2
    assert body["offering_id"].startswith("ls_off_")
    stored = body.get("content") or ""
    assert "Q4 enterprise solution overview with pricing" in stored
    assert "Extracted text from pitch_deck.pdf" in stored
    assert "Extracted text from pricing_guide.docx" in stored
    offering_id = body["offering_id"]

    from app.database.connection import SessionLocal
    from app.offerings.models import OfferingRow

    db = SessionLocal()
    try:
        row = db.query(OfferingRow).filter(OfferingRow.offering_id == offering_id).one()
        assert row.content == stored
        assert "Extracted text from pricing_guide.docx" in (row.content or "")
    finally:
        db.close()

    again = test_client.post("/api/offerings", headers=_auth(pat), json=_payload(org_id))
    assert again.status_code == 200, again.text
    assert again.json()["offering_id"] == offering_id
    assert again.json()["doc_count"] == 2

    listed = test_client.get(f"/api/offerings?organization_id={org_id}", headers=_auth(pat))
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["offering_id"] == offering_id
    assert items[0]["doc_count"] == 2

    more_docs = _docs(
        ("odoc_01M3CP0TVBW0X7NE8THKGNHMCV", "pitch_deck.pdf", "pdf"),
        ("odoc_01M3CP0V39Y68BBAE6RXQBSN5X", "pricing_guide.docx", "docx"),
        ("odoc_01NEWDOC000000000000000001", "faq.txt", "txt"),
    )
    updated = test_client.put(
        f"/api/offerings/{offering_id}",
        headers=_auth(pat),
        json=_payload(org_id, name="Enterprise Pitch Pack Revised", docs=more_docs, doc_count=3),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Enterprise Pitch Pack Revised"
    assert updated.json()["offering_id"] == offering_id
    assert updated.json()["doc_count"] == 3


def test_stores_description_on_offerings_content_when_docs_have_no_text(client):
    test_client, org_id, pat = client
    docs = [
        {
            "doc_id": "odoc_notext_1",
            "file_name": "deck.pptx",
            "file_format": "pptx",
            "s3_key": "offerings/ten_xxx/deck.pptx",
        }
    ]
    resp = test_client.post(
        "/api/offerings",
        headers=_auth(pat),
        json=_payload(org_id, docs=docs, content=None, description="Folder-only description"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["content"] == "Folder-only description"

    from app.database.connection import SessionLocal
    from app.offerings.models import OfferingRow

    db = SessionLocal()
    try:
        row = db.query(OfferingRow).filter(OfferingRow.offering_id == resp.json()["offering_id"]).one()
        assert row.content == "Folder-only description"
    finally:
        db.close()


def test_smartops_rejects_other_org(client):
    test_client, org_id, pat = client
    resp = test_client.post(
        "/api/offerings",
        headers=_auth(pat),
        json=_payload(org_id, organization_id="org_does_not_match"),
    )
    assert resp.status_code == 404


def test_pat_is_not_treated_as_jwt(client):
    """SmartOps PAT must create an offering — never 401 Invalid or expired token."""
    test_client, org_id, pat = client
    resp = test_client.post("/api/offerings", headers=_auth(pat), json=_payload(org_id))
    assert resp.status_code == 201, resp.text
    assert resp.json().get("detail") != "Invalid or expired token"
    assert resp.json()["organization_id"] == org_id


def test_invalid_pat_is_not_reported_as_jwt(client):
    test_client, org_id, _pat = client
    resp = test_client.post(
        "/api/offerings",
        headers=_auth("pat_this_token_does_not_exist_xxxxxx"),
        json=_payload(org_id),
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or revoked PAT"


def _dep_calls(dependant) -> list:
    calls = []
    for dep in getattr(dependant, "dependencies", []) or []:
        if getattr(dep, "call", None) is not None:
            calls.append(dep.call)
        calls.extend(_dep_calls(dep))
    return calls


def test_backend_boot_imports_and_offerings_use_pat_auth(client):
    """Catch UAT boot/import failures and leftover JWT-only offering sync routes."""
    test_client, org_id, pat = client
    from app.main import app
    from app.middleware.pat_auth import get_offering_auth, security
    from app.routers import auth as auth_router
    from fastapi.routing import APIRoute

    assert security is not None
    assert auth_router.bearer_security is security
    assert test_client.get("/health").status_code == 200
    assert test_client.get(
        "/api/v1/integrations/me", headers=_auth(pat)
    ).status_code == 200

    sync_routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = set(route.methods or [])
        if route.path == "/api/offerings" and methods & {"GET", "POST"}:
            sync_routes.append(route)
        if route.path == "/api/offerings/{offering_id}" and "PUT" in methods:
            sync_routes.append(route)

    assert len(sync_routes) >= 3, "GET/POST /api/offerings and PUT /api/offerings/{id} must exist"
    for route in sync_routes:
        calls = _dep_calls(route.dependant)
        assert get_offering_auth in calls, (
            f"{sorted(route.methods)} {route.path} must use get_offering_auth, not JWT-only auth"
        )

