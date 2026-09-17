"""Organization PAT (Personal Access Token) helpers for SmartOps / integrations."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Organization, OrganizationToken
from app.services.seed_service import _new_integration_token, _new_org_id
from app.services.tenant_constants import ORG_TYPE_TENANT, STATUS_ACTIVE

TOKEN_STATUS_ACTIVE = "ACTIVE"
TOKEN_STATUS_REVOKED = "REVOKED"
PAT_PREFIX = "pat_"

ALLOWED_ORG_TYPES = frozenset({"TENANT", "PROVIDER"})


def hash_pat(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_token_id() -> str:
    return f"tok_{secrets.token_hex(12)}"


def _generate_raw_pat() -> str:
    return f"{PAT_PREFIX}{secrets.token_urlsafe(32)}"


def _prefix_of(raw_token: str) -> str:
    # Show enough to recognize the token in UI without revealing the secret.
    return raw_token[:12] + "…" if len(raw_token) > 12 else raw_token


def _scopes_to_json(scopes: list[str] | None) -> str | None:
    if not scopes:
        return None
    cleaned = [s.strip() for s in scopes if s and str(s).strip()]
    return json.dumps(cleaned) if cleaned else None


def scopes_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (TypeError, json.JSONDecodeError):
        pass
    return []


def normalize_org_type(org_type: str | None) -> str:
    value = (org_type or ORG_TYPE_TENANT).strip().upper()
    if value not in ALLOWED_ORG_TYPES:
        raise ValueError(f"Invalid org type. Allowed: {', '.join(sorted(ALLOWED_ORG_TYPES))}")
    return value


def can_manage_org(user, org: Organization) -> bool:
    """Tenant admin of this org, or the LeadSense admin who created it (ops handoff)."""
    if getattr(user, "role", None) != "ADMIN":
        return False
    if getattr(user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
        return False
    if getattr(user, "org_id", None) and user.org_id == org.org_id:
        return True
    if org.created_by_user_id and org.created_by_user_id == getattr(user, "id", None):
        return True
    return False


def create_organization(
    db: Session,
    *,
    name: str,
    org_type: str = ORG_TYPE_TENANT,
    created_by_user_id: int | None = None,
    mint_pat: bool = True,
    pat_name: str | None = None,
) -> tuple[Organization, OrganizationToken | None, str | None]:
    """Create an org and (by default) mint the first PAT — raw returned once."""
    cleaned_name = (name or "").strip()
    if not cleaned_name:
        raise ValueError("Organization name is required")

    org = Organization(
        org_id=_new_org_id(),
        org_name=cleaned_name,
        org_type=normalize_org_type(org_type),
        integration_token=_new_integration_token(),
        status=STATUS_ACTIVE,
        created_by_user_id=created_by_user_id,
    )
    db.add(org)
    db.flush()

    token_row = None
    raw = None
    if mint_pat:
        token_row, raw = create_pat(
            db,
            org=org,
            name=pat_name or "SmartOps",
            created_by_user_id=created_by_user_id,
            commit=False,
        )
    db.commit()
    db.refresh(org)
    if token_row is not None:
        db.refresh(token_row)
    return org, token_row, raw


def create_pat(
    db: Session,
    *,
    org: Organization,
    name: str | None = None,
    scopes: list[str] | None = None,
    created_by_user_id: int | None = None,
    commit: bool = True,
) -> tuple[OrganizationToken, str]:
    if org.status != STATUS_ACTIVE:
        raise ValueError("Cannot create a PAT for a disabled organization")

    raw = _generate_raw_pat()
    row = OrganizationToken(
        token_id=_new_token_id(),
        organization_id=org.org_id,
        token_prefix=_prefix_of(raw),
        token_hash=hash_pat(raw),
        name=(name or "").strip() or None,
        scopes=_scopes_to_json(scopes),
        status=TOKEN_STATUS_ACTIVE,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row, raw


def list_pats(db: Session, org_id: str) -> list[OrganizationToken]:
    return (
        db.query(OrganizationToken)
        .filter(OrganizationToken.organization_id == org_id)
        .order_by(OrganizationToken.created_at.desc())
        .all()
    )


def revoke_pat(db: Session, token: OrganizationToken) -> OrganizationToken:
    if token.status == TOKEN_STATUS_REVOKED:
        return token
    token.status = TOKEN_STATUS_REVOKED
    token.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(token)
    return token


def resolve_active_pat(db: Session, raw_token: str) -> tuple[OrganizationToken, Organization] | None:
    """Hash Bearer PAT → active, non-expired token + org, or None."""
    if not raw_token or not str(raw_token).strip():
        return None
    digest = hash_pat(str(raw_token).strip())
    token = (
        db.query(OrganizationToken)
        .filter(
            OrganizationToken.token_hash == digest,
            OrganizationToken.status == TOKEN_STATUS_ACTIVE,
        )
        .first()
    )
    if not token:
        # Legacy fallback: plaintext organizations.integration_token (seeded before PAT table)
        org = (
            db.query(Organization)
            .filter(
                Organization.integration_token == str(raw_token).strip(),
                Organization.status == STATUS_ACTIVE,
            )
            .first()
        )
        if not org:
            return None
        # Synthesize a transient token view for whoami — do not persist.
        legacy = OrganizationToken(
            token_id="tok_legacy",
            organization_id=org.org_id,
            token_prefix=_prefix_of(raw_token),
            token_hash=digest,
            name="Legacy integration token",
            status=TOKEN_STATUS_ACTIVE,
        )
        return legacy, org

    if token.expires_at is not None:
        exp = token.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return None

    org = db.query(Organization).filter(Organization.org_id == token.organization_id).first()
    if not org or org.status != STATUS_ACTIVE:
        return None

    token.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return token, org


def migrate_legacy_integration_tokens(db: Session) -> int:
    """For orgs with no PAT rows, hash their plaintext integration_token into organization_tokens."""
    migrated = 0
    for org in db.query(Organization).all():
        existing = (
            db.query(OrganizationToken)
            .filter(OrganizationToken.organization_id == org.org_id)
            .count()
        )
        if existing:
            continue
        raw = (org.integration_token or "").strip()
        if not raw or len(raw) < 16:
            continue
        db.add(
            OrganizationToken(
                token_id=_new_token_id(),
                organization_id=org.org_id,
                token_prefix=_prefix_of(raw),
                token_hash=hash_pat(raw),
                name="Legacy integration token",
                status=TOKEN_STATUS_ACTIVE,
            )
        )
        migrated += 1
    if migrated:
        db.commit()
    return migrated
