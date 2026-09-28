"""Conservative classification of inbound email into OOO / reply / bounce / other.

Header signals are preferred; subject/body phrases are fallback only and never
sufficient alone without some automatic-response indicator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import Message

CLASS_OUT_OF_OFFICE = "OUT_OF_OFFICE"
CLASS_NORMAL_REPLY = "NORMAL_REPLY"
CLASS_BOUNCE = "BOUNCE"
CLASS_OTHER = "OTHER"

_OOO_SUBJECT_RE = re.compile(
    r"("
    r"out\s*of\s*office"
    r"|automatic\s+reply"
    r"|auto[\s-]?reply"
    r"|away\s+from\s+(the\s+)?office"
    r"|on\s+vacation"
    r"|currently\s+out"
    r"|ooo\b"
    r")",
    re.IGNORECASE,
)

_OOO_BODY_RE = re.compile(
    r"("
    r"out\s+of\s+(the\s+)?office"
    r"|i\s+am\s+currently\s+out"
    r"|i('|\s+a)?m\s+away\s+from\s+(the\s+)?office"
    r"|automatic\s+reply"
    r"|limited\s+access\s+to\s+(e-?)?mail"
    r"|will\s+return\s+on"
    r")",
    re.IGNORECASE,
)

_BOUNCE_FROM_RE = re.compile(
    r"(mailer-daemon|postmaster|mail-daemon|noreply-bounce)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClassificationResult:
    classification: str
    reason: str


def _header(msg: Message, name: str) -> str:
    value = msg.get(name)
    if value is None:
        return ""
    return str(value).strip()


def _is_auto_submitted(msg: Message) -> bool:
    auto = _header(msg, "Auto-Submitted").lower()
    if auto and auto != "no":
        return True
    precedence = _header(msg, "Precedence").lower()
    if precedence in {"bulk", "junk", "list", "auto_reply", "autoreply"}:
        return True
    if _header(msg, "X-Autoreply").lower() in {"yes", "true", "auto"}:
        return True
    if _header(msg, "X-Auto-Response-Suppress"):
        # Often present on auto-generated traffic; alone not enough for OOO.
        pass
    prefer = _header(msg, "Prefer").lower()
    if "auto-reply" in prefer or "auto_reply" in prefer:
        return True
    # Microsoft Exchange automatic replies
    if _header(msg, "X-MS-Exchange-Inbox-Rules-Loop"):
        return True
    if "auto-submitted" in _header(msg, "X-MS-Exchange-Message-Flags").lower():
        return True
    content_class = _header(msg, "Content-Class").lower()
    if "vnd.ms-exchange.appointment" in content_class:
        return False
    if "msn.messenger" in content_class:
        return False
    return False


def _looks_like_bounce(msg: Message, subject: str, from_addr: str) -> bool:
    ctype = (msg.get_content_type() or "").lower()
    if ctype == "multipart/report":
        return True
    if _header(msg, "X-Failed-Recipients"):
        return True
    if _BOUNCE_FROM_RE.search(from_addr or ""):
        return True
    subj = subject.lower()
    if any(
        phrase in subj
        for phrase in (
            "delivery status notification",
            "undeliverable",
            "delivery failure",
            "mail delivery failed",
            "returned mail",
            "failure notice",
        )
    ):
        return True
    return False


def _ooo_phrase_hit(subject: str, body_text: str) -> bool:
    if _OOO_SUBJECT_RE.search(subject or ""):
        return True
    if body_text and _OOO_BODY_RE.search(body_text[:4000]):
        return True
    return False


def classify_inbound_email(
    msg: Message,
    *,
    body_text: str = "",
    from_email: str = "",
) -> ClassificationResult:
    """Classify a parsed email.Message.

    Conservative rules:
    - Bounce indicators → BOUNCE
    - Automatic response + OOO phrases (or MS auto-reply subject) → OUT_OF_OFFICE
    - Automatic response without OOO evidence → OTHER (not OOO)
    - Human-looking reply (In-Reply-To / References, not auto) → NORMAL_REPLY
    - Else → OTHER
    """
    subject = _header(msg, "Subject")
    from_addr = from_email or _header(msg, "From")

    if _looks_like_bounce(msg, subject, from_addr):
        return ClassificationResult(CLASS_BOUNCE, "bounce_indicators")

    auto = _is_auto_submitted(msg)
    ooo_phrases = _ooo_phrase_hit(subject, body_text)
    # Outlook often prefixes "Automatic reply:" without always setting every header.
    auto_reply_subject = bool(re.match(r"^\s*automatic\s+reply\s*:", subject or "", re.I))

    if auto and (ooo_phrases or auto_reply_subject):
        return ClassificationResult(CLASS_OUT_OF_OFFICE, "auto_headers_and_ooo_signal")

    if auto_reply_subject and ooo_phrases:
        # Subject alone is weak; require body/subject OOO evidence together with
        # Automatic reply prefix (common Outlook pattern even when Auto-Submitted missing).
        return ClassificationResult(CLASS_OUT_OF_OFFICE, "outlook_automatic_reply_subject")

    if auto and not ooo_phrases:
        return ClassificationResult(CLASS_OTHER, "auto_without_ooo_evidence")

    in_reply_to = _header(msg, "In-Reply-To")
    references = _header(msg, "References")
    if (in_reply_to or references) and not auto:
        return ClassificationResult(CLASS_NORMAL_REPLY, "threaded_human_reply")

    # Fallback: clear OOO subject with no bounce/auto — still OTHER unless we
    # have strong phrase + reply threading to our campaign (matcher decides).
    if ooo_phrases and not auto:
        # Without auto headers, do not mark OOO (could be a human saying they'll be out).
        if in_reply_to or references:
            return ClassificationResult(CLASS_NORMAL_REPLY, "human_mentions_ooo")
        return ClassificationResult(CLASS_OTHER, "ooo_phrase_without_auto")

    return ClassificationResult(CLASS_OTHER, "unclassified")
