"""AWS SNS message signature verification.

This endpoint is public (AWS must be able to reach it over the internet) and
its whole job is deciding who gets blacklisted — without verifying the
signature, anyone could POST a fake "bounce" here and get a real customer's
address suppressed. Every message is verified against AWS's signing
certificate before we act on it.

Reference: https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
"""

import base64
import logging
import re

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

# SNS signing certs are always served from an *.amazonaws.com host under the
# sns subdomain — reject anything else to prevent fetching an attacker-chosen
# "certificate" from an arbitrary URL (SSRF / spoofing guard).
_TRUSTED_CERT_URL = re.compile(r"^https://sns\.[a-z0-9-]+\.amazonaws\.com/", re.IGNORECASE)

_cert_cache: dict[str, bytes] = {}

# Field order per SNS message type, per AWS's documented signing scheme.
_SIGNABLE_FIELDS = {
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
    "UnsubscribeConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
}


def _fetch_cert(url: str) -> bytes:
    if url in _cert_cache:
        return _cert_cache[url]
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    _cert_cache[url] = response.content
    return response.content


def _build_string_to_sign(message: dict) -> bytes:
    fields = _SIGNABLE_FIELDS.get(message.get("Type"), [])
    parts = []
    for field in fields:
        if field in message and message[field] is not None:
            parts.append(f"{field}\n{message[field]}\n")
    return "".join(parts).encode("utf-8")


def verify_sns_signature(message: dict) -> bool:
    """Returns True iff the message is authentically signed by AWS SNS."""
    cert_url = message.get("SigningCertURL", "")
    if not _TRUSTED_CERT_URL.match(cert_url):
        logger.warning("Rejected SNS message: untrusted SigningCertURL %r", cert_url)
        return False

    signature = message.get("Signature")
    if not signature:
        logger.warning("Rejected SNS message: missing Signature")
        return False

    try:
        cert = x509.load_pem_x509_certificate(_fetch_cert(cert_url))
        public_key = cert.public_key()

        string_to_sign = _build_string_to_sign(message)
        signature_bytes = base64.b64decode(signature)
        digest = hashes.SHA256() if message.get("SignatureVersion") == "2" else hashes.SHA1()

        public_key.verify(signature_bytes, string_to_sign, padding.PKCS1v15(), digest)
        return True
    except InvalidSignature:
        logger.warning("Rejected SNS message: signature verification failed")
        return False
    except Exception:
        logger.exception("Error verifying SNS signature")
        return False
