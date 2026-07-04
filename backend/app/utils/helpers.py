"""Utility helpers."""

import re
from datetime import datetime, timezone


def extract_placeholders(text: str) -> list[str]:
    """Extract {{Placeholder}} tokens from template text."""
    return list(dict.fromkeys(re.findall(r"\{\{(\w+)\}\}", text)))


def render_template(text: str, context: dict[str, str]) -> str:
    """Replace {{Key}} placeholders with context values."""
    result = text
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_campaign_id(prefix: str = "CMP") -> str:
    """Generate a unique campaign ID string."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{ts}"
