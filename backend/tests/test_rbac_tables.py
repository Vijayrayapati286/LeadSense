"""Provider/tenant configuration tables — no tenants table."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import inspect

_TEST_DB = Path(__file__).resolve().parent / "rbac_tables_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ.setdefault("USE_MOCK_SES", "true")
os.environ.setdefault("USE_MOCK_GROQ", "true")
os.environ.setdefault("USE_MOCK_S3", "true")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")


REQUIRED_TABLES = {
    "organizations",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
    "invites",
    "user_email_verifications",
    "refresh_tokens",
    "password_reset_tokens",
}


@pytest.fixture()
def db_session(monkeypatch):
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

    from app.database.connection import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        if hasattr(conn_mod.engine, "dispose"):
            conn_mod.engine.dispose()
        try:
            _TEST_DB.unlink(missing_ok=True)
        except OSError:
            pass


def test_required_tables_exist_without_tenants(db_session):
    tables = set(inspect(db_session.get_bind()).get_table_names())
    missing = REQUIRED_TABLES - tables
    assert not missing, f"missing tables: {sorted(missing)}"
    assert "tenants" not in tables
    assert "sectors" not in tables
    assert "manager_assignments" not in tables


def test_rbac_catalog_seeded(db_session):
    from app.models import Permission, Role, RolePermission

    names = {r.name for r in db_session.query(Role).all()}
    assert {"owner", "admin", "user", "manager", "trainee", "provider_admin"} <= names
    perm_names = {row.name for row in db_session.query(Permission).all()}
    assert {
        "campaigns:read",
        "linkedin:extract",
        "icp:read",
        "offerings:write",
        "members:invite",
        "orgs:onboard",
        "integrations:manage",
    } <= perm_names
    assert "training:use" not in perm_names
    assert "hierarchy:manage" not in perm_names
    assert "org:create" not in perm_names
    assert db_session.query(RolePermission).count() > 0


def test_user_roles_backfilled_for_seeded_admins(db_session):
    from app.models import User, UserRole
    from app.services.rbac_service import has_permission

    admin = db_session.query(User).filter(User.email == "admin1@tenant.com").first()
    assert admin is not None
    assignments = db_session.query(UserRole).filter(UserRole.user_id == admin.id).all()
    assert assignments
    assert all(row.organization_id == admin.org_id for row in assignments)
    assert has_permission(db_session, admin, "members:invite")
    assert has_permission(db_session, admin, "campaigns:send")
    assert not has_permission(db_session, admin, "orgs:onboard")


def test_application_permissions_by_role(db_session):
    from app.models import User
    from app.services.rbac_service import has_permission, user_permissions

    tenant_admin = db_session.query(User).filter(User.email == "admin1@tenant.com").first()
    provider_admin = db_session.query(User).filter(User.email == "provider.admin@feuji.com").first()
    provider_user = db_session.query(User).filter(User.email == "provider.user@feuji.com").first()
    assert tenant_admin and provider_admin and provider_user

    assert "linkedin:extract" in user_permissions(db_session, tenant_admin)
    assert "members:manage" in user_permissions(db_session, tenant_admin)
    assert "orgs:onboard" not in user_permissions(db_session, tenant_admin)

    assert has_permission(db_session, provider_admin, "orgs:onboard")
    assert has_permission(db_session, provider_admin, "members:invite")
    assert has_permission(db_session, provider_user, "campaigns:read")
    assert not has_permission(db_session, provider_user, "members:invite")
    assert not has_permission(db_session, provider_user, "orgs:onboard")


def test_no_sector_or_manager_assignment_tables(db_session):
    tables = set(inspect(db_session.get_bind()).get_table_names())
    assert "sectors" not in tables
    assert "manager_assignments" not in tables
