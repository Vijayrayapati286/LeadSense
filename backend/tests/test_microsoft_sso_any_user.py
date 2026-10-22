"""Microsoft SSO accepts any Azure AD user; CORE_USERS only gates dev-login."""

from __future__ import annotations

from app.database.connection import SessionLocal
from app.models import Organization
from app.services.auth_service import AuthService


def test_microsoft_upsert_allows_non_core_feuji_user(client):
    db = SessionLocal()
    try:
        user = AuthService()._upsert_user(
            db,
            {
                "id": "azure-oid-sreelatha",
                "mail": "nagasreelatha.goriparthi@feuji.com",
                "userPrincipalName": "nagasreelatha.goriparthi@feuji.com",
                "displayName": "Nagasreelatha Goriparthi",
                "department": "Engineering",
            },
            require_allowlist=False,
        )
        assert user.email == "nagasreelatha.goriparthi@feuji.com"
        assert user.status == "ACTIVE"
        org = db.query(Organization).filter(Organization.org_id == user.org_id).first()
        assert org is not None
        assert org.org_name == "Feuji"
    finally:
        db.close()


def test_dev_login_still_requires_core_users(client):
    resp = client.post(
        "/api/auth/dev-login",
        json={"email": "nagasreelatha.goriparthi@feuji.com", "name": "Nagasreelatha"},
    )
    assert resp.status_code == 403
