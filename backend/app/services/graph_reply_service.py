"""Automatic reply detection via Microsoft Graph — polls each rep's mailbox
for new mail and matches it back to a prior send by Message-ID.

Ships inert: every entry point below no-ops (logs, returns) unless both
`settings.enable_reply_polling` is true AND the Azure AD app registration
behind AZURE_CLIENT_ID has been granted the Mail.Read Application permission
with admin consent (acquire_token_for_client below simply fails, harmlessly,
until then). See the implementation plan for the exact activation steps.
"""

import logging
from datetime import datetime, timedelta

import httpx
import msal
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import SessionLocal
from app.models import EmailLog, MailboxSyncState, User
from app.services import event_service
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
settings = get_settings()

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


def _get_graph_token() -> str | None:
    """App-only (client-credentials) token — no signed-in user, unlike the
    delegated flow auth_service.py uses for SSO login. Returns None (never
    raises) whenever Graph access isn't actually available yet, which is what
    keeps this feature safe to ship before admin consent exists."""
    if not settings.is_azure_configured:
        return None
    try:
        app = msal.ConfidentialClientApplication(
            client_id=settings.azure_client_id,
            client_credential=settings.azure_client_secret,
            authority=settings.azure_authority,
        )
        result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        if "access_token" not in result:
            logger.warning(
                "Graph app-only token unavailable (%s) — reply polling stays inactive until "
                "Mail.Read Application permission is granted with admin consent",
                result.get("error_description", result.get("error", "unknown error")),
            )
            return None
        return result["access_token"]
    except Exception:
        logger.exception("Failed to acquire Graph token")
        return None


def _fetch_new_messages(token: str, user_email: str, since: datetime) -> list[dict]:
    url = f"{GRAPH_BASE_URL}/users/{user_email}/mailFolders/inbox/messages"
    params = {
        "$filter": f"receivedDateTime ge {since.isoformat()}",
        "$select": "id,receivedDateTime,from,internetMessageHeaders",
        "$top": "50",
        "$orderby": "receivedDateTime asc",
    }
    try:
        response = httpx.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
        response.raise_for_status()
        return response.json().get("value", [])
    except Exception:
        logger.exception("Graph mailbox fetch failed for %s", user_email)
        return []


def _extract_referenced_ids(message: dict) -> set[str]:
    """Message-IDs this inbound mail is threaded to — In-Reply-To (the
    immediate parent) plus every entry in References (the whole thread) —
    checking both maximizes match rate across mail clients that don't
    populate them identically."""
    ids: set[str] = set()
    for header in message.get("internetMessageHeaders", []):
        name = header.get("name", "").lower()
        value = header.get("value", "")
        if name == "in-reply-to":
            ids.add(value.strip())
        elif name == "references":
            ids.update(v.strip() for v in value.split() if v.strip())
    return ids


def _process_mailbox(db: Session, token: str, user: User) -> None:
    sync_state = db.query(MailboxSyncState).filter(MailboxSyncState.user_id == user.id).first()
    if not sync_state:
        sync_state = MailboxSyncState(user_id=user.id, last_synced_at=None)
        db.add(sync_state)
        db.flush()

    since = sync_state.last_synced_at or (utc_now() - timedelta(days=1))
    messages = _fetch_new_messages(token, user.email, since)

    latest_seen = since
    for message in messages:
        received_at = message.get("receivedDateTime")
        if received_at:
            received_dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            latest_seen = max(latest_seen, received_dt)

        referenced_ids = _extract_referenced_ids(message)
        if not referenced_ids:
            continue

        matched_log = db.query(EmailLog).filter(EmailLog.message_id.in_(referenced_ids)).first()
        if not matched_log:
            continue

        sender_email = message.get("from", {}).get("emailAddress", {}).get("address")
        if not sender_email:
            continue

        logger.info(
            "Reply detected for campaign %d from %s (matched EmailLog %d)",
            matched_log.campaign_id, sender_email, matched_log.id,
        )
        event_service.handle_reply(db, sender_email, campaign_id=matched_log.campaign_id)

    sync_state.last_synced_at = latest_seen
    db.commit()


def poll_all_mailboxes(db: Session) -> None:
    if not settings.enable_reply_polling:
        return

    token = _get_graph_token()
    if not token:
        return

    for user in db.query(User).all():
        try:
            _process_mailbox(db, token, user)
        except Exception:
            logger.exception("Reply polling failed for mailbox %s", user.email)
            db.rollback()


def poll_replies() -> None:
    """Scheduler entry point — own session, mirrors scheduler_service.py's
    process_due_followups/process_queued_initial_sends shape."""
    db: Session = SessionLocal()
    try:
        poll_all_mailboxes(db)
    except Exception:
        logger.exception("Error polling for replies")
        db.rollback()
    finally:
        db.close()
