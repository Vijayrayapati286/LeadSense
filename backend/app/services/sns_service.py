"""AWS SNS alerts. Publishing failures never propagate to callers."""

from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

BOUNCE_RATE_ALERT_THRESHOLD = 2.0

# Campaigns already alerted while above the threshold. Cleared when the rate
# falls back to the threshold or below, so a later rise can alert again.
# In-process only: a restart or another worker can publish once more.
_alerted_campaigns: set[str] = set()


def clear_bounce_alert_cache() -> None:
    """Test helper. Forgets which campaigns have already been alerted."""
    _alerted_campaigns.clear()


def format_bounce_rate(bounce_rate: float) -> str:
    rounded = round(float(bounce_rate), 2)
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def bounce_rate_from_recipient_stats(stats: dict) -> float:
    """Percent from the bounced and sent counts already produced by recipient_stats."""
    sent = int(stats.get("sent") or 0)
    bounced = int(stats.get("bounced") or 0)
    if sent <= 0:
        return 0.0
    return round((bounced / sent) * 100, 2)


def _alert_key(campaign_name: str, campaign_id: int | None) -> str:
    if campaign_id is not None:
        return f"id:{campaign_id}"
    return f"name:{(campaign_name or '').strip()}"


def _sns_client():
    import boto3

    settings = get_settings()
    region = (settings.sns_region or settings.aws_region or "us-east-1").strip()
    kwargs: dict = {"region_name": region}
    access_key = (settings.aws_access_key_id or "").strip()
    secret_key = (settings.aws_secret_access_key or "").strip()
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("sns", **kwargs)


def send_bounce_alert(
    bounce_rate: float,
    campaign_name: str,
    campaign_id: int | None = None,
) -> None:
    """Publish when bounce_rate is strictly above 2%. Never raises."""
    name = (campaign_name or "").strip() or "Unknown campaign"
    try:
        rate = float(bounce_rate)
    except (TypeError, ValueError):
        logger.error("Bounce rate alert skipped: invalid bounce_rate=%r campaign=%s", bounce_rate, name)
        return

    key = _alert_key(name, campaign_id)
    if rate <= BOUNCE_RATE_ALERT_THRESHOLD:
        _alerted_campaigns.discard(key)
        logger.info(
            "Bounce rate %.2f%% for campaign %s is at or below 2%% — SNS alert skipped",
            rate,
            name,
        )
        return

    if key in _alerted_campaigns:
        logger.info(
            "Bounce rate alert already sent for campaign %s (%.2f%%) — skipping duplicate",
            name,
            rate,
        )
        return

    settings = get_settings()
    topic_arn = (settings.sns_topic_arn or "").strip()
    if not topic_arn:
        logger.error(
            "SNS bounce alert skipped: SNS_TOPIC_ARN is not configured (campaign=%s bounce_rate=%.2f%%)",
            name,
            rate,
        )
        return

    formatted = format_bounce_rate(rate)
    message = (
        "LeadSense Bounce Rate Alert\n"
        "\n"
        f"Campaign: {name}\n"
        "\n"
        f"Bounce Rate: {formatted}\n"
        "\n"
        "Alert: Bounce rate has exceeded the 2% threshold."
    )
    try:
        client = _sns_client()
        client.publish(
            TopicArn=topic_arn,
            Subject="LeadSense Bounce Rate Alert",
            Message=message,
        )
    except Exception as exc:
        logger.error(
            "SNS bounce alert publish failed campaign=%s bounce_rate=%s: %s",
            name,
            formatted,
            exc,
        )
        return

    _alerted_campaigns.add(key)
    logger.info("Bounce rate alert triggered campaign=%s bounce_rate=%s", name, formatted)
