"""AWS SES email sending service with mock fallback."""

import logging
import random
import uuid

from app.config import get_settings
from app.utils.helpers import render_template

logger = logging.getLogger(__name__)
settings = get_settings()


class SESService:
    def __init__(self):
        self.settings = settings
        self._client = None

    def _get_client(self):
        if self._client is None and not self.settings.use_mock_ses:
            try:
                import boto3

                self._client = boto3.client(
                    "ses",
                    region_name=self.settings.aws_region,
                    aws_access_key_id=self.settings.aws_access_key_id,
                    aws_secret_access_key=self.settings.aws_secret_access_key,
                )
            except Exception as exc:
                logger.warning("Failed to initialize SES client, using mock: %s", exc)
        return self._client

    def _get_delivery_address(self, to_email: str) -> str:
        if self.settings.test_email_override:
            return self.settings.test_email_override
        return to_email

    def send_email(self, to_email: str, subject: str, body_html: str, body_text: str | None = None) -> dict:
        """Send a single email via AWS SES or mock."""
        delivery_to = self._get_delivery_address(to_email)
        if self.settings.use_mock_ses or not self._get_client():
            return self._mock_send(delivery_to, subject, original_recipient=to_email)

        try:
            response = self._client.send_email(
                Source=self.settings.aws_ses_sender_email,
                Destination={"ToAddresses": [delivery_to]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                        "Text": {"Data": body_text or body_html, "Charset": "UTF-8"},
                    },
                },
            )
            return {"status": "sent", "message_id": response["MessageId"], "error": None}
        except Exception as exc:
            logger.error("SES send failed for %s: %s", to_email, exc)
            return {"status": "failed", "message_id": None, "error": str(exc)}

    def send_bulk_email(
        self,
        recipients: list[dict],
        subject_template: str,
        body_template: str,
    ) -> dict:
        """
        Send bulk emails with placeholder replacement.

        Each recipient dict should have: email, name, company, designation, industry
        """
        sent, failed, pending = 0, 0, 0
        details = []

        for recipient in recipients:
            context = {
                "Name": recipient.get("name", ""),
                "Email": recipient.get("email", ""),
                "Company": recipient.get("company", ""),
                "Designation": recipient.get("designation", ""),
                "Industry": recipient.get("industry", ""),
            }

            rendered_subject = render_template(subject_template, context)
            rendered_body = render_template(body_template, context)
            rendered_html = f"<html><body>{rendered_body.replace(chr(10), '<br>')}</body></html>"

            result = self.send_email(
                to_email=recipient["email"],
                subject=rendered_subject,
                body_html=rendered_html,
                body_text=rendered_body,
            )

            status = result["status"]
            if status == "sent":
                sent += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1

            details.append({
                "recipient_email": recipient["email"],
                "recipient_name": recipient.get("name", ""),
                "status": status,
                "message_id": result.get("message_id"),
                "error": result.get("error"),
            })

        return {"sent": sent, "failed": failed, "pending": pending, "details": details}

    def _mock_send(self, to_email: str, subject: str, original_recipient: str | None = None) -> dict:
        """Simulate email sending for development."""
        # Simulate ~90% success rate
        if random.random() < 0.9:
            return {
                "status": "sent",
                "message_id": f"mock-{uuid.uuid4().hex[:12]}",
                "error": None,
                "delivered_to": to_email,
                "original_recipient": original_recipient or to_email,
            }
        return {
            "status": "failed",
            "message_id": None,
            "error": "Mock failure: simulated SES error",
            "delivered_to": to_email,
            "original_recipient": original_recipient or to_email,
        }
