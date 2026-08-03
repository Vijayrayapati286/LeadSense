"""AWS SES email sending service with mock fallback."""

import base64
import logging
import random
import re
import uuid
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from app.config import get_settings
from app.utils.helpers import KNOWN_MERGE_FIELDS, render_email_body, render_template

logger = logging.getLogger(__name__)
settings = get_settings()

# Matches a base64 data-URI <img> src, e.g. src="data:image/png;base64,AAAA..."
# — captures the subtype (png/jpeg/...) and payload separately so each can be
# pulled out into its own inline MIME part.
_DATA_URI_IMG_RE = re.compile(
    r'(<img\b[^>]*\bsrc=")data:image/([a-zA-Z0-9.+-]+);base64,([^"]+)(")',
    re.IGNORECASE,
)


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

    def _build_source(self, from_name: str | None, reply_to: str | None) -> str:
        """Build the SES Source (From) header. Display name is the sending
        rep's real name (from their SSO user record); the address's local
        part is personalized too — e.g. vijay.rayapati@mail.feuji.com for a
        rep whose real address is vijay.rayapati@feuji.com — landed on the
        dedicated sending domain (aws_ses_sending_domain, falling back to
        aws_ses_sender_email's own domain when unset) rather than the org's
        real mail domain, so bulk sends don't affect that domain's sender
        reputation/DMARC alignment. This relies on that whole domain (not
        just one address on it) being domain-verified in SES, since every
        rep's local part needs to be authorized to send from it; falls back
        to the single configured sender address when there's no sender
        identity to personalize from.

        `reply_to` is only read here to derive that local part — it's
        already the rep's real address wherever this is called from (see
        send_email's reply_to param) and is passed to SES completely
        unchanged as ReplyToAddresses below, so Reply-To behavior itself
        doesn't change."""
        sender_domain = self.settings.aws_ses_sending_domain or self.settings.aws_ses_sender_email.rsplit("@", 1)[-1]
        address = self.settings.aws_ses_sender_email
        if reply_to and "@" in reply_to:
            address = f"{reply_to.split('@', 1)[0]}@{sender_domain}"
        if from_name:
            return f'"{from_name}" <{address}>'
        return address

    def _extract_inline_images(self, body_html: str) -> tuple[str, list[tuple[str, str, bytes]]]:
        """Pull base64 data-URI <img> sources out of the HTML into separate
        inline images, rewriting each src to a `cid:` reference. Outlook (and
        several other mail clients) silently drop data: URI images entirely —
        CID-embedded images, sent as MIME parts referenced by Content-ID,
        render everywhere instead. Returns (rewritten_html, images), where
        each image is (content_id, subtype, raw_bytes)."""
        images: list[tuple[str, str, bytes]] = []

        def _replace(match: re.Match) -> str:
            prefix, subtype, b64data, suffix = match.groups()
            try:
                raw = base64.b64decode(b64data)
            except Exception:
                return match.group(0)
            content_id = uuid.uuid4().hex
            images.append((content_id, subtype, raw))
            return f"{prefix}cid:{content_id}{suffix}"

        rewritten = _DATA_URI_IMG_RE.sub(_replace, body_html)
        return rewritten, images

    def _build_raw_message(
        self,
        source: str,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str | None,
        reply_to: str | None,
    ) -> MIMEMultipart:
        rewritten_html, images = self._extract_inline_images(body_html)

        msg_root = MIMEMultipart("related")
        msg_root["Subject"] = str(Header(subject, "utf-8"))
        display_name, address = parseaddr(source)
        msg_root["From"] = formataddr((str(Header(display_name, "utf-8")), address)) if display_name else address
        msg_root["To"] = to_email
        if reply_to:
            msg_root["Reply-To"] = reply_to

        msg_alt = MIMEMultipart("alternative")
        msg_root.attach(msg_alt)
        msg_alt.attach(MIMEText(body_text or rewritten_html, "plain", "utf-8"))
        msg_alt.attach(MIMEText(rewritten_html, "html", "utf-8"))

        for content_id, subtype, raw in images:
            img_part = MIMEImage(raw, _subtype=subtype)
            img_part.add_header("Content-ID", f"<{content_id}>")
            img_part.add_header("Content-Disposition", "inline", filename=f"{content_id}.{subtype}")
            msg_root.attach(img_part)

        return msg_root

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
            source = self._build_source(from_name, reply_to)
            raw_message = self._build_raw_message(source, delivery_to, subject, body_html, body_text, reply_to)

            response = self._client.send_raw_email(
                Source=source,
                Destinations=[delivery_to],
                RawMessage={"Data": raw_message.as_bytes()},
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
