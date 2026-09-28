"""Sample raw MIME fixtures for local OOO / reply / bounce classification tests."""

from __future__ import annotations


def outlook_ooo(*, from_email: str, to_email: str, in_reply_to: str, message_id: str = "<ooo-1@example.com>") -> bytes:
    return f"""From: {from_email}
To: {to_email}
Subject: Automatic reply: Quick question
Message-ID: {message_id}
In-Reply-To: {in_reply_to}
References: {in_reply_to}
Auto-Submitted: auto-replied
Prefer: auto-reply
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

I am currently out of the office and will return on Monday.
""".encode("utf-8")


def generic_auto_reply_no_ooo_phrase(*, from_email: str, to_email: str, in_reply_to: str) -> bytes:
    """Auto-submitted but not OOO — should classify as OTHER, not OUT_OF_OFFICE."""
    return f"""From: {from_email}
To: {to_email}
Subject: Auto-Notification
Message-ID: <auto-other@example.com>
In-Reply-To: {in_reply_to}
Auto-Submitted: auto-replied
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Your ticket has been received.
""".encode("utf-8")


def ooo_without_exact_phrase(*, from_email: str, to_email: str, in_reply_to: str) -> bytes:
    return f"""From: {from_email}
To: {to_email}
Subject: Automatic Reply: Re your note
Message-ID: <ooo-2@example.com>
In-Reply-To: {in_reply_to}
Auto-Submitted: auto-replied
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

I am away from the office until next week with limited access to email.
""".encode("utf-8")


def normal_human_reply(*, from_email: str, to_email: str, in_reply_to: str) -> bytes:
    return f"""From: {from_email}
To: {to_email}
Subject: Re: Quick question
Message-ID: <human-1@example.com>
In-Reply-To: {in_reply_to}
References: {in_reply_to}
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Thanks — happy to chat next week.
""".encode("utf-8")


def bounce_dsn(*, to_email: str, original_recipient: str) -> bytes:
    return f"""From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>
To: {to_email}
Subject: Delivery Status Notification (Failure)
Message-ID: <bounce-1@google.com>
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="b1"

--b1
Content-Type: text/plain; charset=utf-8

Delivery failed for {original_recipient}

--b1
Content-Type: message/delivery-status

Final-Recipient: rfc822; {original_recipient}
Action: failed
Status: 5.1.1

--b1--
""".encode("utf-8")


def malformed_bytes() -> bytes:
    return b"\xff\xfe this is not a valid email\x00\x01"
