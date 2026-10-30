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

    local = to_email.split("@", 1)[0].lower()
    if "karthik" in local or "koundinya" in local or "kowndinya" in local:
        greeting = "Karthik"
    else:
        greeting = local.split(".", 1)[0].replace("_", " ").title()

    subject = f"Hi {greeting}"
    body_text = (
        f"Hi {greeting},\n\n"
        "Hope you are doing well. Just checking if this note reached you.\n\n"
        "Thanks,\n"
        "Sreelatha\n"
    )
    body_html = f"""
    <html>
      <body>
        <p>Hi {greeting},</p>
        <p>Hope you are doing well. Just checking if this note reached you.</p>
        <p>Thanks,<br>Sreelatha</p>
      </body>
    </html>
    """

    result = svc.send_email(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        from_name="Sreelatha",
        reply_to=settings.aws_ses_sender_email,
        add_unsubscribe=False,
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
