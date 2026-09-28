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
    offering_id = body["offering_id"]

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


def test_smartops_rejects_other_org(client):
    test_client, org_id, pat = client
    resp = test_client.post(
        "/api/offerings",
        headers=_auth(pat),
        json=_payload(org_id, organization_id="org_does_not_match"),
    )
    assert resp.status_code == 404
