"""Provider credit balances shown on Settings. External calls are mocked."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.credit_balance_service import get_provider_credits
from app.services.millionverifier_service import MillionVerifierAuthError


def _settings(**overrides):
    values = dict(
        millionverifier_enabled=True,
        use_mock_millionverifier=False,
        millionverifier_api_key="mv-secret",
        apify_token="apify-secret",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Client:
    def __init__(self, timeout=None):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        self.calls.append(url)
        assert headers["Authorization"] == "Bearer apify-secret"
        if url.endswith("/users/me"):
            return _Response({"data": {"plan": {"monthlyUsageCreditsUsd": 29}}})
        return _Response({"data": {"totalUsageCreditsUsdAfterVolumeDiscount": 10.5}})


def test_millionverifier_and_apify_remaining(monkeypatch):
    monkeypatch.setattr("app.services.credit_balance_service.get_settings", lambda: _settings())

    class _Verifier:
        def __init__(self, settings=None):
            pass

        def check_credits(self):
            return {"credits": 4200}

    monkeypatch.setattr("app.services.credit_balance_service.MillionVerifierService", _Verifier)
    monkeypatch.setattr("app.services.credit_balance_service.httpx.Client", _Client)

    result = get_provider_credits()
    assert result["millionverifier"]["status"] == "ok"
    assert result["millionverifier"]["credits_remaining"] == 4200
    assert result["apify"]["status"] == "ok"
    assert result["apify"]["credits_remaining"] == 18.5
    assert result["apify"]["credits_used"] == 10.5
    assert result["apify"]["credits_limit"] == 29
    dumped = str(result)
    assert "mv-secret" not in dumped
    assert "apify-secret" not in dumped


def test_missing_credentials_are_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.services.credit_balance_service.get_settings",
        lambda: _settings(millionverifier_api_key="", apify_token="", use_mock_millionverifier=False),
    )
    result = get_provider_credits()
    assert result["millionverifier"]["status"] == "not_configured"
    assert result["millionverifier"]["credits_remaining"] is None
    assert result["apify"]["status"] == "not_configured"
    assert result["apify"]["credits_remaining"] is None


def test_millionverifier_mock_mode(monkeypatch):
    monkeypatch.setattr(
        "app.services.credit_balance_service.get_settings",
        lambda: _settings(use_mock_millionverifier=True, apify_token=""),
    )
    result = get_provider_credits()
    assert result["millionverifier"]["status"] == "mock"


def test_provider_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr("app.services.credit_balance_service.get_settings", lambda: _settings())

    class _Verifier:
        def __init__(self, settings=None):
            pass

        def check_credits(self):
            raise MillionVerifierAuthError("nope")

    class _FailClient:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return _Response({}, status_code=403)

    monkeypatch.setattr("app.services.credit_balance_service.MillionVerifierService", _Verifier)
    monkeypatch.setattr("app.services.credit_balance_service.httpx.Client", _FailClient)
    result = get_provider_credits()
    assert result["millionverifier"]["status"] == "unavailable"
    assert result["apify"]["status"] == "unavailable"
