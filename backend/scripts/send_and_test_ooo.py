"""Send a real SES test mail and run the OOO inbound classifier against it.

Usage (from backend folder, or inside the backend container):
  python scripts/send_and_test_ooo.py nagasreelatha.goriparthi@feuji.com
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.config import get_settings
from app.database.connection import SessionLocal
from app.models import Campaign, CampaignRecipient, EmailLog, Recipient, User
from app.services import inbound_email_service
from app.services.ses_service import SESService
from app.utils.helpers import utc_now
from tests.fixtures import ooo_samples

DEFAULT_TO = "nagasreelatha.goriparthi@feuji.com"


def _send(to_email: str) -> dict:
    settings = get_settings()
    svc = SESService()
    svc.settings = settings
    greeting = to_email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
    result = svc.send_email(
        to_email=to_email,
        subject="LeadSense test — please check Inbox vs Junk",
        body_html=f"""
        <html>
          <body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2937;line-height:1.6;">
            <p>Hi {greeting},</p>
            <p>This is a <strong>test email from LeadSense</strong>.</p>
            <p>Please tell us if it landed in <strong>Inbox</strong> or <strong>Junk</strong>.</p>
            <p>If you do not want more test mail, use <strong>Unsubscribe</strong> in your email client.</p>
          </body>
        </html>
        """,
        body_text=(
            f"Hi {greeting},\n\n"
            "This is a test email from LeadSense.\n"
            "Please tell us if it landed in Inbox or Junk.\n\n"
            "If you do not want more test mail, use Unsubscribe in your email client.\n"
        ),
        from_name="LeadSense",
        reply_to=settings.aws_ses_sender_email,
    )
    print(f"to={to_email}")
    print(f"mock_ses={settings.use_mock_ses}")
    print(f"status={result.get('status')}")
    print(f"message_id={result.get('message_id')}")
    print(f"ses_message_id={result.get('ses_message_id')}")
    if result.get("error"):
        print(f"error={result['error']}")
    return result


def _run_ooo_pipeline(to_email: str, send_result: dict) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin1@tenant.com").first()
        if user is None:
            user = db.query(User).filter(User.role.in_(["TENANT_ADMIN", "ADMIN"])).first()
        if user is None:
            print("ooo_test=fail reason=no_tenant_user")
            return 1

        email_norm = to_email.strip().lower()
        recipient = (
            db.query(Recipient)
            .filter(func.lower(Recipient.email) == email_norm, Recipient.org_id == user.org_id)
            .first()
        )
        if recipient is None:
            recipient = Recipient(
                name="Naga Sreelatha",
                email=email_norm,
                company="Feuji",
                org_id=user.org_id,
            )
            db.add(recipient)
            db.flush()

        campaign = (
            db.query(Campaign)
            .filter(Campaign.campaign_id == "CMP-OOO-TEST", Campaign.org_id == user.org_id)
            .first()
        )
        if campaign is None:
            campaign = Campaign(
                campaign_name="OOO pipeline test",
                campaign_id="CMP-OOO-TEST",
                owner=user.name,
                user_id=user.id,
                org_id=user.org_id,
                status="active",
            )
            db.add(campaign)
            db.flush()

        cr = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.recipient_id == recipient.id,
            )
            .first()
        )
        if cr is None:
            cr = CampaignRecipient(
                campaign_id=campaign.id,
                recipient_id=recipient.id,
                status="sent",
                last_sent_at=utc_now(),
                sender_user_id=user.id,
            )
            db.add(cr)
            db.flush()
        else:
            cr.status = "sent"
            cr.last_sent_at = utc_now()
            cr.ooo_at = None
            cr.next_send_at = None

        mime_id = send_result.get("message_id") or f"<ooo-test-{uuid.uuid4().hex[:10]}@outreach.feuji.com>"
        log = EmailLog(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status="sent" if send_result.get("status") == "sent" else (send_result.get("status") or "failed"),
            sender_user_id=user.id,
            message_id=mime_id,
            ses_message_id=send_result.get("ses_message_id"),
            subject="LeadSense test — please check Inbox vs Junk",
        )
        db.add(log)
        db.commit()

        raw = ooo_samples.exchange_ooo_without_auto_submitted(
            from_email=email_norm,
            to_email=get_settings().aws_ses_sender_email,
            in_reply_to=mime_id,
            message_id=f"<ooo-live-{uuid.uuid4().hex[:10]}@feuji.com>",
        )
        result = inbound_email_service.process_raw_inbound(db, raw)
        db.refresh(cr)
        print(f"ooo_classification={result.classification}")
        print(f"ooo_matched={result.matched}")
        print(f"ooo_campaign_id={result.campaign_id}")
        print(f"ooo_detail={result.detail}")
        print(f"recipient_status={cr.status}")
        print(f"recipient_ooo_at={cr.ooo_at}")
        if result.classification == "OUT_OF_OFFICE" and result.matched and cr.status == "out_of_office":
            print("ooo_test=pass")
            return 0
        print("ooo_test=fail")
        return 1
    finally:
        db.close()


def main(to_email: str) -> int:
    send_result = _send(to_email)
    if send_result.get("status") != "sent":
        print("send=fail — still running OOO classifier against a local log")
    return _run_ooo_pipeline(to_email, send_result)


if __name__ == "__main__":
    target = sys.argv[1].strip() if len(sys.argv) > 1 else DEFAULT_TO
    sys.exit(main(target))
