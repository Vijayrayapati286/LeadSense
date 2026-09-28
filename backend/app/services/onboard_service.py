"""Provider onboarding: tenant org + owner verify email + member invites."""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Invite, Organization, User, UserEmailVerification
from app.services import invite_service, organization_token_service as pat_service
from app.services.auth_service import AuthService
from app.services.rbac_service import assign_system_role
from app.services.ses_service import SESService
from app.services.tenant_constants import ROLE_ADMIN, STATUS_ACTIVE, STATUS_INACTIVE
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)

VERIFY_TTL_HOURS = 72
ses = SESService()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _new_verify_id() -> str:
    return f"uev_{secrets.token_hex(12)}"


def issue_email_verification(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserEmailVerification(
            id=_new_verify_id(),
            user_id=user.id,
            code=token,
            expires_at=utc_now() + timedelta(hours=VERIFY_TTL_HOURS),
        )
    )
    db.flush()
    return token


def owner_verify_url(token: str) -> str:
    return f"{get_settings().frontend_url}/verify-email?token={token}"


def invite_accept_url(token: str) -> str:
    return f"{get_settings().frontend_url}/accept-invite?token={token}"


def send_owner_verification_email(user: User, org: Organization, token: str) -> str:
    url = owner_verify_url(token)
    org_name = html.escape(org.org_name or "")
    safe_url = html.escape(url)
    subject = f"Verify your email — admin for {org.org_name}"
    body_html = (
        f"<p>Hello {html.escape(user.name)},</p>"
        f"<p>You are the admin for <strong>{org_name}</strong>. "
        f"This access is only for that tenant organization.</p>"
        f"<p>Verify this email and set your password:</p>"
        f'<p><a href="{safe_url}">{safe_url}</a></p>'
        f"<p>This link expires in {VERIFY_TTL_HOURS} hours.</p>"
    )
    result = ses.send_email(user.email, subject, body_html, body_text=f"Verify and set password: {url}")
    logger.info(
        "Owner verification email to %s status=%s url=%s",
        user.email,
        result.get("status"),
        url,
    )
    return url


def send_invite_verification_email(invite: Invite, org: Organization | None = None) -> str:
    url = invite_accept_url(invite.invite_token)
    org_name = html.escape((org.org_name if org else None) or invite.org_id)
    safe_url = html.escape(url)
    subject = f"You're invited to {org.org_name if org else 'LeadSense'}"
    body_html = (
        f"<p>You were invited to join <strong>{org_name}</strong> as "
        f"<strong>{html.escape(invite.role)}</strong>.</p>"
        f"<p>Verify this email and set your password:</p>"
        f'<p><a href="{safe_url}">{safe_url}</a></p>'
        f"<p>This invite expires in {invite_service.INVITE_TTL_DAYS} days.</p>"
    )
    result = ses.send_email(invite.email, subject, body_html, body_text=f"Accept invite: {url}")
    logger.info(
        "Invite verification email to %s status=%s url=%s",
        invite.email,
        result.get("status"),
        url,
    )
    return url


def onboard_tenant(
    db: Session,
    *,
    org_name: str,
    client_name: str | None = None,
    owner_name: str,
    owner_email: str,
    created_by: User,
    pat_name: str | None = None,
) -> tuple[Organization, object, str, User, str]:
    email = owner_email.strip().lower()
    name = owner_name.strip()
    if not name:
        raise ValueError("Admin name is required")
    client = (client_name or name).strip()
    if db.query(User).filter(User.email == email).first():
        raise ValueError("A user with that email already exists")

    org, token_row, raw = pat_service.create_organization(
        db,
        name=org_name,
        org_type="TENANT",
        client_name=client,
        created_by_user_id=created_by.id,
        mint_pat=True,
        pat_name=pat_name or "SmartOps",
    )

    owner = User(
        name=name,
        email=email,
        department="Admin",
        org_id=org.org_id,
        role=ROLE_ADMIN,
        status=STATUS_INACTIVE,
        password_hash=None,
    )
    db.add(owner)
    db.flush()
    org.owner_user_id = owner.id
    assign_system_role(db, owner, "owner")

    verify_token = issue_email_verification(db, owner)
    verify_url = send_owner_verification_email(owner, org, verify_token)
    db.commit()
    db.refresh(org)
    db.refresh(owner)
    if token_row is not None:
        db.refresh(token_row)
    return org, token_row, raw, owner, verify_url


def get_owner_verification(db: Session, token: str) -> UserEmailVerification:
    row = (
        db.query(UserEmailVerification)
        .filter(UserEmailVerification.code == token)
        .order_by(UserEmailVerification.created_at.desc())
        .first()
    )
    if not row:
        raise ValueError("Invalid or expired verification link")
    if row.verified_at is not None:
        raise ValueError("This email is already verified")
    expires = _as_utc(row.expires_at)
    if expires and expires < utc_now():
        raise ValueError("This verification link has expired")
    return row


def complete_owner_verification(db: Session, token: str, *, password: str, name: str | None = None) -> User:
    row = get_owner_verification(db, token)
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise ValueError("Invalid or expired verification link")
    if name and name.strip():
        user.name = name.strip()
    user.password_hash = AuthService.hash_password(password)
    user.status = STATUS_ACTIVE
    user.email_verified_at = utc_now()
    row.verified_at = utc_now()
    db.commit()
    db.refresh(user)
    return user


def get_pending_invite(db: Session, token: str) -> Invite:
    invite = db.query(Invite).filter(Invite.invite_token == token).first()
    if not invite:
        raise ValueError("Invalid or expired invite")
    invite_service._expire_stale(db, invite.org_id)
    db.refresh(invite)
    if invite.status == invite_service.STATUS_EXPIRED:
        raise ValueError("Invite has expired")
    if invite.status != invite_service.STATUS_PENDING:
        raise ValueError("This invite is no longer pending")
    return invite


def complete_invite(db: Session, token: str, *, name: str, password: str) -> tuple[Invite, User]:
    invite = get_pending_invite(db, token)
    invite, user = invite_service.accept_invite(
        db,
        invite,
        name=name,
        password=password,
        actor=None,
    )
    user.email_verified_at = utc_now()
    assign_system_role(db, user, "admin" if user.role == ROLE_ADMIN else "user")
    db.commit()
    db.refresh(user)
    return invite, user
