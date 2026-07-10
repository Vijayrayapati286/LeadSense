"""Utility helpers."""

import html
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


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE = re.compile(r"^[-•*]\s+")


def markdown_to_html(text: str) -> str:
    """Render a small markdown subset (**bold**, "- " bullet lists, blank-line
    paragraphs) into inline-styled HTML suitable for an email body. Input is
    HTML-escaped first so recipient/company data can't inject markup."""
    if not text:
        return ""

    escaped = html.escape(text)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)

    parts = []
    for block in re.split(r"\n\s*\n", escaped.strip()):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if all(_BULLET_RE.match(line) for line in lines):
            items = "".join(
                f'<li style="margin-bottom:6px;">{_BULLET_RE.sub("", line)}</li>' for line in lines
            )
            parts.append(
                f'<ul style="margin:0 0 16px 0;padding-left:20px;list-style-type:disc;">{items}</ul>'
            )
        else:
            parts.append(f'<p style="margin:0 0 16px 0;">{"<br>".join(lines)}</p>')

    return "".join(parts)


def markdown_to_plain(text: str) -> str:
    """Strip markdown emphasis markers for the plain-text email fallback."""
    if not text:
        return ""
    return _BOLD_RE.sub(r"\1", text)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_campaign_id(prefix: str = "CMP") -> str:
    """Generate a unique campaign ID string."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{ts}"
