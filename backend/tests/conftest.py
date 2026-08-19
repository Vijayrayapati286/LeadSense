"""Shared fixtures for BuildE2E LinkedIn profile extractor tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Must run before any app.* import so Settings + engine pick SQLite.
_TEST_DB = Path(__file__).resolve().parent / "bulk_email_e2e_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["USE_SQLITE_FALLBACK"] = "true"
os.environ["SKIP_BULK_RESUME"] = "1"
os.environ.setdefault("BULK_RETRY_BASE_DELAY_SECONDS", "0")
os.environ.setdefault("APIFY_MAX_RETRIES", "5")
os.environ.setdefault("USE_MOCK_SES", "true")
os.environ.setdefault("USE_MOCK_GROQ", "true")

try:
    _TEST_DB.unlink(missing_ok=True)
except OSError:
    pass


@pytest.fixture()
def client(monkeypatch):
    # Patch the service module first, then re-bind names used by FastAPI lifespan.
    import app.services.scheduler_service as scheduler_service

    monkeypatch.setattr(scheduler_service, "start_scheduler", lambda: None)
    monkeypatch.setattr(scheduler_service, "stop_scheduler", lambda: None)

    from app.config import get_settings

    get_settings.cache_clear()

    from app import main as main_module
    from app.middleware.auth import get_current_user
    from app.models import User
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)

    async def _override_current_user():
        return User(id=1, name="Test User", email="test@example.com", department="Test")

    main_module.app.dependency_overrides[get_current_user] = _override_current_user
    from app.linkedin.rate_limit import bulk_extract_limiter, profile_extract_limiter

    bulk_extract_limiter._hits.clear()
    profile_extract_limiter._hits.clear()
    with TestClient(main_module.app) as test_client:
        yield test_client
    main_module.app.dependency_overrides.clear()
