"""Utility helpers."""

import html
import re
from datetime import datetime, timezone

import bleach
from bleach.css_sanitizer import CSSSanitizer


def extract_placeholders(text: str) -> list[str]:
    """Extract {{Placeholder}} tokens from template text."""
    return list(dict.fromkeys(re.findall(r"\{\{(\w+)\}\}", text)))


# Every {{Key}} -> Recipient column a template can merge in, matching the
# mandatory prospect-info header set (Name, Email, Company, Designation,
# Designation Level, Industry, Department, Country, State, City, Company
# Size, Years of Experience, Skills, Source, Status). Kept in sync with
# frontend/src/utils/mergeFields.js — mirrored there since preview rendering
# happens client-side.
KNOWN_MERGE_FIELDS: dict[str, str] = {
    "Name": "name",
    "Email": "email",
    "Company": "company",
    "Designation": "designation",
    "DesignationLevel": "designation_level",
    "Industry": "industry",
    "Department": "department",
    "Country": "country",
    "State": "state",
    "City": "city",
    "CompanySize": "company_size",
    "YearsOfExperience": "years_of_experience",
    "Skills": "skills",
    "Source": "source",
    "Status": "status",
}


def build_recipient_context(recipient) -> dict[str, str]:
    """Build the {{Key}}: value context for rendering a template against a
    real Recipient row — every known merge field, plus any approved custom
    fields (RecipientCustomValue) this recipient has a value for."""
    context = {key: (getattr(recipient, field, None) or "") for key, field in KNOWN_MERGE_FIELDS.items()}
    for cv in getattr(recipient, "custom_values", []) or []:
        context[cv.custom_field.name] = cv.value or ""
    return context


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


# ── Manual template rich-text HTML (WYSIWYG editor) ─────────────────────────
# The Manual template type stores real HTML from a TipTap rich text editor
# instead of the markdown-lite subset above. This is the server-side trust
# boundary for that HTML — the client (DOMPurify) sanitizes too, but only the
# server-side pass is actually trusted, since a client can be bypassed.

_RICH_TEXT_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u", "s", "span", "div", "ul", "ol", "li", "a",
    "table", "thead", "tbody", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "hr", "img", "sub", "sup",
]
_RICH_TEXT_ATTRS = {
    "*": ["style"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
# No "data" here deliberately — data: URIs are handled separately below via
# an explicit image-mimetype allowlist rather than bleach's bare-scheme check,
# since bleach can't distinguish data:image/png from data:text/html.
_RICH_TEXT_PROTOCOLS = ["http", "https", "mailto"]
_RICH_TEXT_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color", "background-color", "font-family", "font-size", "font-weight",
        "font-style", "text-align", "text-decoration", "line-height",
        "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
        "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
        "border", "border-collapse", "width", "height",
    ]
)
_DATA_IMAGE_SRC_RE = re.compile(r'src="(data:image/(?:png|jpe?g|gif|webp|bmp);base64,[A-Za-z0-9+/=]+)"')


def sanitize_html(rich_html: str) -> str:
    """Sanitize a Manual template's rich-text body before it's persisted.
    Strips script/style/event-handler content and unknown tags/protocols
    while preserving normal WYSIWYG formatting (bold, colors, alignment,
    lists, tables, links) and pasted base64 images specifically — bleach's
    protocol allowlist only understands bare schemes, not image/* data URIs,
    so those are stashed behind a placeholder before cleaning and restored
    after, rather than trusting bleach's coarser data: handling."""
    if not rich_html:
        return rich_html

    placeholders: dict[str, str] = {}

    def _stash(match: re.Match) -> str:
        token = f"__DATA_IMG_{len(placeholders)}__"
        placeholders[token] = match.group(1)
        return f'src="{token}"'

    stashed = _DATA_IMAGE_SRC_RE.sub(_stash, rich_html)

    cleaned = bleach.clean(
        stashed,
        tags=_RICH_TEXT_TAGS,
        attributes=_RICH_TEXT_ATTRS,
        protocols=_RICH_TEXT_PROTOCOLS,
        css_sanitizer=_RICH_TEXT_CSS_SANITIZER,
        strip=True,
    )

    for token, data_uri in placeholders.items():
        cleaned = cleaned.replace(token, data_uri)

    return cleaned


def sanitize_manual_body(data: dict) -> dict:
    """Sanitize `data["body"]` in place when the payload is a Manual
    template — the single choke point shared by campaign_service's
    save_template/update_template and MailerService's create/update, so
    every save path for Manual content goes through the same trust
    boundary regardless of caller."""
    if data.get("type") == "manual" and data.get("body"):
        data["body"] = sanitize_html(data["body"])
    return data


def render_email_body(body: str, content_type: str, context: dict[str, str]) -> tuple[str, str]:
    """Return (html, plain_text) for a rendered, ready-to-send template body.

    Manual bodies are already-sanitized HTML from the rich text editor and
    are merge-field-substituted as-is; every other template type keeps the
    existing markdown-lite rendering (markdown_to_html/markdown_to_plain)."""
    rendered = render_template(body, context)
    if content_type == "manual":
        plain_text = bleach.clean(rendered, tags=[], attributes={}, strip=True)
        return rendered, plain_text
    return markdown_to_html(rendered), markdown_to_plain(rendered)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_campaign_id(prefix: str = "CMP") -> str:
    """Generate a unique campaign ID string."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{ts}"
