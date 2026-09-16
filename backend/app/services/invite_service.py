"""Tenant invite management service."""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Invite, User
from app.services.auth_service import AuthService
from app.utils.helpers import utc_now

INVITE_TTL_DAYS = 7
STATUS_PENDING = "PENDING"
STATUS_ACCEPTED = "ACCEPTED"
STATUS_CANCELLED = "CANCELLED"
STATUS_EXPIRED = "EXPIRED"


def _expire_stale(db: Session, org_id: str) -> None:
    now = utc_now()
    stale = (
        db.query(Invite)
        .filter(
            Invite.org_id == org_id,
            Invite.status == STATUS_PENDING,
            Invite.expires_at < now,
        )
        .all()
    )
    for invite in stale:
        invite.status = STATUS_EXPIRED
        invite.resolved_at = now
        invite.resolved_note = "Invite expired"
    if stale:
        db.commit()


def list_invites(
    db: Session,
    org_id: str,
    *,
    status: str | None = None,
    search: str = "",
) -> list[Invite]:
    _expire_stale(db, org_id)
    query = db.query(Invite).filter(Invite.org_id == org_id)
    if status and status.upper() != "ALL":
        query = query.filter(Invite.status == status.upper())
    if search.strip():
        query = query.filter(Invite.email.ilike(f"%{search.strip()}%"))
    return query.order_by(Invite.created_at.desc()).all()


def create_invite(
    db: Session,
    *,
    org_id: str,
    email: str,
    role: str,
    invited_by: User,
) -> Invite:
    _expire_stale(db, org_id)
    email = email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise ValueError("A user with that email already exists")

    pending = (
        db.query(Invite)
        .filter(
            Invite.org_id == org_id,
            Invite.email == email,
            Invite.status == STATUS_PENDING,
        )
        .first()
    )
    if pending:
        raise ValueError("A pending invite already exists for that email")

    invite = Invite(
        org_id=org_id,
        email=email,
        role=role,
        status=STATUS_PENDING,
        invite_token=secrets.token_urlsafe(24),
        invited_by_user_id=invited_by.id,
        expires_at=utc_now() + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def cancel_invite(db: Session, invite: Invite, actor: User) -> Invite:
    if invite.status != STATUS_PENDING:
        raise ValueError("Only pending invites can be cancelled")
    invite.status = STATUS_CANCELLED
    invite.resolved_at = utc_now()
    invite.resolved_note = f"Cancelled by {actor.name} on {utc_now().strftime('%m/%d/%Y')}"
    db.commit()
    db.refresh(invite)
    return invite


def accept_invite(
    db: Session,
    invite: Invite,
    *,
    name: str,
    password: str,
    actor: User,
) -> tuple[Invite, User]:
    _expire_stale(db, invite.org_id)
    db.refresh(invite)
    if invite.status == STATUS_EXPIRED:
        raise ValueError("Invite has expired")
    if invite.status != STATUS_PENDING:
        raise ValueError("Only pending invites can be accepted")

    existing = db.query(User).filter(User.email == invite.email).first()
    if existing:
        raise ValueError("A user with that email already exists")

    user = User(
        name=name.strip() or invite.email.split("@")[0],
        email=invite.email,
        department="Sales",
        org_id=invite.org_id,
        role=invite.role,
        status="ACTIVE",
        password_hash=AuthService.hash_password(password),
    )
    db.add(user)
    invite.status = STATUS_ACCEPTED
    invite.resolved_at = utc_now()
    invite.resolved_note = f"Accepted by {actor.name} on {utc_now().strftime('%m/%d/%Y')}"
    db.commit()
    db.refresh(invite)
    db.refresh(user)
    return invite, user


def invite_to_dict(invite: Invite) -> dict:
    invited_by = invite.invited_by
    return {
        "id": invite.id,
        "org_id": invite.org_id,
        "email": invite.email,
        "role": invite.role,
        "status": invite.status,
        "invited_by": invited_by.name if invited_by else None,
        "invited_by_user_id": invite.invited_by_user_id,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        "resolved_at": invite.resolved_at.isoformat() if invite.resolved_at else None,
        "resolved_note": invite.resolved_note,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
    }
