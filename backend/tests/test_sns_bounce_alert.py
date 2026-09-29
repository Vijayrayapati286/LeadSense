"""Bounce-rate SNS alerts. Publishing is mocked; campaign flow must not raise."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest

from app.services.event_service import _maybe_publish_bounce_alerts
from app.services.sns_service import clear_bounce_alert_cache, send_bounce_alert


class _Settings:
    def __init__(self, topic_arn="arn:aws:sns:us-east-1:123456789012:leadsense-bounces"):
        self.sns_topic_arn = topic_arn
        self.sns_region = "us-east-1"
        self.aws_region = "us-east-1"
        self.aws_access_key_id = ""
        self.aws_secret_access_key = ""


@pytest.fixture(autouse=True)
def _reset_alerts():
    clear_bounce_alert_cache()
    yield
    clear_bounce_alert_cache()


@pytest.fixture
def sns(monkeypatch):
    publish = MagicMock()
    client = MagicMock()
    client.publish = publish
    monkeypatch.setattr(boto3, "client", MagicMock(return_value=client))
    monkeypatch.setattr("app.services.sns_service.get_settings", lambda: _Settings())
    return publish


def test_bounce_rate_1_5_does_not_publish(sns):
    send_bounce_alert(1.5, "ABC Campaign", campaign_id=1)
    sns.assert_not_called()


def test_bounce_rate_exactly_2_does_not_publish(sns):
    send_bounce_alert(2.0, "ABC Campaign", campaign_id=1)
    sns.assert_not_called()


def test_bounce_rate_2_1_publishes_campaign_name_and_rate(sns):
    send_bounce_alert(2.1, "ABC Campaign", campaign_id=1)
    sns.assert_called_once()
    kwargs = sns.call_args.kwargs
    assert kwargs["Subject"] == "LeadSense Bounce Rate Alert"
    assert "Campaign: ABC Campaign" in kwargs["Message"]
    assert "Bounce Rate: 2.1%" in kwargs["Message"]
    assert "exceeded the 2% threshold" in kwargs["Message"]


def test_sns_publish_failure_does_not_raise(sns):
    sns.side_effect = RuntimeError("sns down")
    send_bounce_alert(2.8, "ABC Campaign", campaign_id=1)
    sns.assert_called_once()


def test_missing_topic_arn_is_skipped(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setattr("app.services.sns_service.get_settings", lambda: _Settings(topic_arn=""))
    send_bounce_alert(3.0, "ABC Campaign", campaign_id=1)
    client.assert_not_called()


def test_duplicate_alert_is_not_published_again(sns):
    send_bounce_alert(2.1, "ABC Campaign", campaign_id=1)
    send_bounce_alert(2.8, "ABC Campaign", campaign_id=1)
    sns.assert_called_once()


def _hook(monkeypatch, stats, publish):
    monkeypatch.setattr("app.services.sns_service.get_settings", lambda: _Settings())
    monkeypatch.setattr(boto3, "client", MagicMock(return_value=MagicMock(publish=publish)))

    class _Service:
        def recipient_stats(self, db, campaign_id):
            return stats

    monkeypatch.setattr("app.services.campaign_service.CampaignService", lambda: _Service())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=7, campaign_name="ABC Campaign"
    )
    _maybe_publish_bounce_alerts(db, [7])


def test_hook_uses_recipient_stats_without_publishing_at_or_below_threshold(monkeypatch):
    publish = MagicMock()
    _hook(monkeypatch, {"sent": 1000, "bounced": 15}, publish)
    publish.assert_not_called()
    clear_bounce_alert_cache()
    _hook(monkeypatch, {"sent": 1000, "bounced": 20}, publish)
    publish.assert_not_called()


def test_hook_publishes_name_and_rate_from_existing_stats(monkeypatch):
    publish = MagicMock()
    _hook(monkeypatch, {"sent": 1000, "bounced": 21}, publish)
    publish.assert_called_once()
    message = publish.call_args.kwargs["Message"]
    assert "Campaign: ABC Campaign" in message
    assert "Bounce Rate: 2.1%" in message


def test_hook_survives_stats_failure(monkeypatch):
    class _Service:
        def recipient_stats(self, db, campaign_id):
            raise RuntimeError("db read failed")

    monkeypatch.setattr("app.services.campaign_service.CampaignService", lambda: _Service())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=7, campaign_name="ABC Campaign"
    )
    _maybe_publish_bounce_alerts(db, [7])
