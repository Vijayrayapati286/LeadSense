"""AWS SES email sending service with mock fallback."""

import logging
import random
import uuid

from app.config import get_settings
from app.utils.helpers import KNOWN_MERGE_FIELDS, render_email_body, render_template

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

                region = self.settings.ses_region or self.settings.aws_region
                # SES-specific credentials take priority — needed when the
                # sending identity (e.g. mail.feuji.com) is verified in a
                # different AWS account than the compute's IAM role, which
                # has no access to another account's SES identities no
                # matter its permissions. Fall back to the generic AWS keys,
                # then to the instance's IAM role via boto3's default
                # credential chain, for same-account setups (local dev, or
                # a role that legitimately owns the sending identity).
                access_key = self.settings.ses_aws_access_key_id or self.settings.aws_access_key_id
                secret_key = self.settings.ses_aws_secret_access_key or self.settings.aws_secret_access_key

                kwargs = {"region_name": region}
                if access_key and secret_key:
                    kwargs["aws_access_key_id"] = access_key
                    kwargs["aws_secret_access_key"] = secret_key

                self._client = boto3.client("ses", **kwargs)
            except Exception as exc:
                logger.warning("Failed to initialize SES client, using mock: %s", exc)
        return self._client

    def _get_delivery_address(self, to_email: str) -> str:
        if self.settings.test_email_override:
            return self.settings.test_email_override
        return to_email

    def _build_source(self, from_name: str | None) -> str:
        """Build the SES Source header. Display name is the sending rep's
        real name (from their SSO user record); the address stays the single
        verified SES sender identity — swapping AWS_SES_SENDER_EMAIL to the
        isolated go.feuji.com subdomain address, once that identity exists in
        SES/DNS, requires no further code change here."""
        if from_name:
            return f'"{from_name}" <{self.settings.aws_ses_sender_email}>'
        return self.settings.aws_ses_sender_email

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
    ) -> dict:
        """Send a single email via AWS SES or mock."""
        delivery_to = self._get_delivery_address(to_email)
        if self.settings.use_mock_ses or not self._get_client():
            return self._mock_send(delivery_to, subject, original_recipient=to_email)

        try:
            kwargs = {
                "Source": self._build_source(from_name),
                "Destination": {"ToAddresses": [delivery_to]},
                "Message": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                        "Text": {"Data": body_text or body_html, "Charset": "UTF-8"},
                    },
                },
            }
            if reply_to:
                kwargs["ReplyToAddresses"] = [reply_to]

            response = self._client.send_email(**kwargs)
            return {"status": "sent", "message_id": response["MessageId"], "error": None}
        except Exception as exc:
            logger.error("SES send failed for %s: %s", to_email, exc)
            return {"status": "failed", "message_id": None, "error": str(exc)}

    def send_bulk_email(
        self,
        recipients: list[dict],
        subject_template: str,
        body_template: str,
        from_name: str | None = None,
        reply_to: str | None = None,
        content_type: str = "placeholder",
    ) -> dict:
        """
        Send bulk emails with placeholder replacement.

        Each recipient dict maps merge-field keys (Name, Email, Company, ...
        every key in KNOWN_MERGE_FIELDS) to values; any field the caller
        didn't supply just renders blank.
        """
        sent, failed, pending = 0, 0, 0
        details = []

        for recipient in recipients:
            context = {key: recipient.get(field, "") for key, field in KNOWN_MERGE_FIELDS.items()}

            rendered_subject = render_template(subject_template, context)
            body_html, body_text = render_email_body(body_template, content_type, context)
            rendered_html = (
                '<html><body style="font-family:Arial,Helvetica,sans-serif;'
                'font-size:14px;color:#1f2937;line-height:1.6;">'
                f"{body_html}</body></html>"
            )

            result = self.send_email(
                to_email=recipient["email"],
                subject=rendered_subject,
                body_html=rendered_html,
                body_text=body_text,
                from_name=from_name,
                reply_to=reply_to,
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
