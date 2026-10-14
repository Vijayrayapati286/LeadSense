"""Send one LeadSense test email through SES (same From/Reply-To/unsubscribe path).

Usage:
  python scripts/send_test_mail.py sunhith.musuku@feuji.com
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services.ses_service import SESService


def main(to_email: str) -> int:
    settings = get_settings()
    svc = SESService()
    svc.settings = settings

    subject = "LeadSense test — please check Inbox vs Junk"
    body_text = (
        "Hi Sunhith,\n\n"
        "This is a test email from LeadSense.\n"
        "Please tell us if it landed in Inbox or Junk.\n\n"
        "If you do not want more test mail, use Unsubscribe in your email client.\n"
    )
    body_html = """
    <html>
      <body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2937;line-height:1.6;">
        <p>Hi Sunhith,</p>
        <p>This is a <strong>test email from LeadSense</strong>.</p>
        <p>Please tell us if it landed in <strong>Inbox</strong> or <strong>Junk</strong>.</p>
        <p>If you do not want more test mail, use <strong>Unsubscribe</strong> in your email client.</p>
      </body>
    </html>
    """

    result = svc.send_email(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        from_name="LeadSense",
        reply_to=settings.aws_ses_sender_email,
    )
    print(f"to={to_email}")
    print(f"mock_ses={settings.use_mock_ses}")
    print(f"status={result.get('status')}")
    print(f"ses_message_id={result.get('ses_message_id')}")
    if result.get("error"):
        print(f"error={result['error']}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test_mail.py you@feuji.com", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1].strip()))
