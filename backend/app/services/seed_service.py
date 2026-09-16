"""Seed database with sample data for development."""

from datetime import datetime, timedelta
import json
import logging
import random
import re
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Campaign, EmailLog, Organization, Recipient, Template, User
from app.services.auth_service import AuthService
from app.services.core_users import CORE_USERS
from app.services.tenant_constants import (
    ADMIN_DEFS,
    DEFAULT_TENANT_KEY,
    TENANT_DEFS,
)

logger = logging.getLogger(__name__)

# Predictable placeholders like TOKEN-001 / same-as-org_id must never ship as
# real integration tokens — regenerate them to a cryptographically unique value.
_WEAK_TOKEN_RE = re.compile(r"^TOKEN-\d+$", re.IGNORECASE)
# Predictable org PKs like TENANT-001 must be rotated to opaque org_<hex> ids.
_WEAK_ORG_ID_RE = re.compile(r"^TENANT-\d+$", re.IGNORECASE)

# Child tables that store organizations.org_id as a foreign key.
_ORG_FK_TABLES = (
    "users",
    "invites",
    "campaigns",
    "recipients",
    "mailers",
    "recipient_groups",
    "tags",
)


def _new_integration_token() -> str:
    """Return a unique opaque token (not derived from org_id)."""
    return secrets.token_urlsafe(32)


def _new_org_id() -> str:
    """Return a unique opaque org primary key, e.g. org_a1b2c3d4e5f67890."""
    return f"org_{secrets.token_hex(12)}"


def _is_weak_integration_token(token: str | None, org_id: str | None = None) -> bool:
    if not token or not str(token).strip():
        return True
    value = str(token).strip()
    if org_id and value == org_id:
        return True
    if _WEAK_TOKEN_RE.match(value):
        return True
    if len(value) < 16:
        return True
    return False


def _is_weak_org_id(org_id: str | None) -> bool:
    if not org_id or not str(org_id).strip():
        return True
    return bool(_WEAK_ORG_ID_RE.match(str(org_id).strip()))


def _table_exists(db: Session, table: str) -> bool:
    bind = db.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        row = db.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).first()
        return row is not None
    row = db.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    ).first()
    return row is not None


def rename_organization_id(db: Session, old_id: str, new_id: str) -> None:
    """Rename an organization PK and cascade FK updates across tenant tables."""
    if old_id == new_id:
        return
    org = db.query(Organization).filter(Organization.org_id == old_id).first()
    if not org:
        return
    if db.query(Organization).filter(Organization.org_id == new_id).first():
        raise ValueError(f"Target org_id already exists: {new_id}")

    # Free the unique integration_token on the old row before inserting the copy.
    kept_token = org.integration_token
    org.integration_token = f"__migrating__{old_id}__{secrets.token_hex(8)}"
    db.flush()

    replacement = Organization(
        org_id=new_id,
        org_name=org.org_name,
        org_type=org.org_type,
        integration_token=kept_token,
        status=org.status,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )
    db.add(replacement)
    db.flush()

    for table in _ORG_FK_TABLES:
        if not _table_exists(db, table):
            continue
        db.execute(
            text(f"UPDATE {table} SET org_id = :new_id WHERE org_id = :old_id"),
            {"new_id": new_id, "old_id": old_id},
        )

    db.delete(org)
    db.flush()
    logger.info("Renamed organization %s → %s", old_id, new_id)


def ensure_unique_org_ids(db: Session) -> dict[str, str]:
    """Rotate any TENANT-00x (or empty) org_id values to unique org_<hex> ids.

    Returns a map of {old_org_id: new_org_id} for ids that were changed.
    """
    used = {o.org_id for o in db.query(Organization).all()}
    renamed: dict[str, str] = {}

    for org in list(db.query(Organization).order_by(Organization.org_id).all()):
        if not _is_weak_org_id(org.org_id):
            continue
        old_id = org.org_id
        candidate = None
        for _ in range(20):
            candidate = _new_org_id()
            if candidate not in used:
                break
        if not candidate or candidate in used:
            candidate = _new_org_id()
        used.discard(old_id)
        used.add(candidate)
        rename_organization_id(db, old_id, candidate)
        renamed[old_id] = candidate

    if renamed:
        db.commit()
        logger.info("Rotated %s weak org_id value(s) to opaque org_* ids", len(renamed))
    return renamed


def ensure_unique_integration_tokens(db: Session) -> None:
    """Rotate any missing or predictable integration_token values for all orgs."""
    used = {
        (o.integration_token or "").strip()
        for o in db.query(Organization).all()
        if o.integration_token
    }
    changed = False
    for org in db.query(Organization).order_by(Organization.org_id).all():
        if not _is_weak_integration_token(org.integration_token, org.org_id):
            continue
        for _ in range(10):
            candidate = _new_integration_token()
            if candidate not in used:
                break
        else:
            candidate = _new_integration_token()
        used.discard((org.integration_token or "").strip())
        used.add(candidate)
        org.integration_token = candidate
        changed = True
        logger.info("Rotated integration_token for %s to a unique opaque value", org.org_id)
    if changed:
        db.commit()


def _find_org_for_tenant_def(db: Session, tenant: dict) -> Organization | None:
    """Resolve an org by display name, then by known legacy TENANT-00x ids."""
    org = (
        db.query(Organization)
        .filter(Organization.org_name == tenant["org_name"])
        .first()
    )
    if org:
        return org
    for legacy in tenant.get("legacy_org_ids") or ():
        org = db.query(Organization).filter(Organization.org_id == legacy).first()
        if org:
            return org
    return None


def resolve_org_id_by_tenant_key(db: Session, tenant_key: str) -> str | None:
    tenant = next((t for t in TENANT_DEFS if t["tenant_key"] == tenant_key), None)
    if not tenant:
        return None
    org = _find_org_for_tenant_def(db, tenant)
    return org.org_id if org else None


def get_default_tenant_org_id(db: Session) -> str | None:
    """Admin 1 / Tenant One org_id (opaque). Used for orphan + core user mapping."""
    org_id = resolve_org_id_by_tenant_key(db, DEFAULT_TENANT_KEY)
    if org_id:
        return org_id
    admin = db.query(User).filter(User.email == "admin1@tenant.com").first()
    if admin and admin.org_id:
        return admin.org_id
    first = db.query(Organization).order_by(Organization.created_at).first()
    return first.org_id if first else None


def provision_tenants(db: Session) -> None:
    """Ensure seeded tenants + ADMIN users exist with unique opaque org_ids."""
    for tenant in TENANT_DEFS:
        org = _find_org_for_tenant_def(db, tenant)
        if not org:
            org_id = _new_org_id()
            org = Organization(
                org_id=org_id,
                org_name=tenant["org_name"],
                org_type=tenant["org_type"],
                integration_token=_new_integration_token(),
                status=tenant["status"],
            )
            db.add(org)
            logger.info("Created organization %s (%s)", org_id, tenant["org_name"])
        else:
            org.org_name = tenant["org_name"]
            org.org_type = tenant["org_type"]
            org.status = tenant["status"]
            if _is_weak_integration_token(org.integration_token, org.org_id):
                org.integration_token = _new_integration_token()

    db.flush()
    ensure_unique_org_ids(db)
    ensure_unique_integration_tokens(db)

    for admin in ADMIN_DEFS:
        org_id = resolve_org_id_by_tenant_key(db, admin["tenant_key"])
        if not org_id:
            logger.error(
                "Cannot provision admin %s — tenant %s missing",
                admin["email"],
                admin["tenant_key"],
            )
            continue

        user = db.query(User).filter(User.email == admin["email"]).first()
        if not user:
            user = User(
                name=admin["name"],
                email=admin["email"],
                department="Admin",
                org_id=org_id,
                role=admin["role"],
                status=admin["status"],
                password_hash=AuthService.hash_password(admin["password"]),
            )
            db.add(user)
            logger.info("Created tenant admin %s → %s", admin["email"], org_id)
        else:
            user.name = admin["name"]
            user.org_id = org_id
            user.role = admin["role"]
            user.status = admin["status"]
            user.password_hash = AuthService.hash_password(admin["password"])

    db.commit()


def assign_orphan_users_to_admin1(db: Session) -> int:
    """Map every user with no org_id to Tenant One (Admin 1). Leaves other tenants alone."""
    default_org_id = get_default_tenant_org_id(db)
    if not default_org_id:
        logger.warning("No default tenant found — skipping orphan user assignment")
        return 0

    orphans = db.query(User).filter(User.org_id.is_(None)).all()
    if not orphans:
        return 0
    for user in orphans:
        user.org_id = default_org_id
        if not getattr(user, "role", None):
            user.role = "USER"
        if not getattr(user, "status", None):
            user.status = "ACTIVE"
    db.commit()
    logger.info(
        "Assigned %s orphan user(s) to %s (Admin 1 / Tenant One)",
        len(orphans),
        default_org_id,
    )
    return len(orphans)


def provision_core_users(db: Session) -> None:
    """Get-or-create each named team member and map them to Tenant One (Admin 1)."""
    default_org_id = get_default_tenant_org_id(db)
    try:
        passwords = json.loads(get_settings().core_user_passwords_json or "{}")
    except (TypeError, ValueError):
        logger.warning("CORE_USER_PASSWORDS is not valid JSON — no passwords provisioned this run")
        passwords = {}

    for name, email in CORE_USERS:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=name,
                email=email,
                department="Sales",
                org_id=default_org_id,
                role="USER",
                status="ACTIVE",
            )
            db.add(user)
        else:
            user.name = name
            if not user.org_id and default_org_id:
                user.org_id = default_org_id

        password = passwords.get(email)
        if password:
            user.password_hash = AuthService.hash_password(password)
        elif not user.password_hash:
            logger.warning(
                "No password configured for %s — password login unavailable until CORE_USER_PASSWORDS is set",
                email,
            )
    db.commit()
    assign_orphan_users_to_admin1(db)


def seed_dummy_data(db: Session) -> None:
    """Populate database with realistic sample data."""
    default_org_id = get_default_tenant_org_id(db)

    user = User(
        name="Demo User",
        email="demo@company.com",
        department="Sales",
        org_id=default_org_id,
        role="USER",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()

    recipients_data = [
        ("John Smith", "john.smith@acme.com", "Acme Corp", "CEO", "Technology"),
        ("Jane Doe", "jane.doe@techcorp.io", "TechCorp", "CTO", "Software"),
        ("Robert Johnson", "robert.j@globalinc.com", "Global Inc", "VP Sales", "Finance"),
        ("Emily Chen", "emily.chen@startup.co", "StartupCo", "Founder", "SaaS"),
        ("Michael Brown", "michael.b@enterprise.com", "Enterprise Ltd", "Director", "Manufacturing"),
        ("Sarah Wilson", "sarah.w@innovate.io", "InnovateIO", "CMO", "Marketing"),
        ("David Lee", "david.lee@fintech.com", "FinTech Pro", "CFO", "Finance"),
        ("Lisa Anderson", "lisa.a@healthtech.com", "HealthTech", "COO", "Healthcare"),
        ("James Taylor", "james.t@retailmax.com", "RetailMax", "VP Marketing", "Retail"),
        ("Anna Martinez", "anna.m@cloudsys.com", "CloudSys", "Engineer", "Cloud"),
    ]

    recipients = []
    for name, email, company, designation, industry in recipients_data:
        r = Recipient(
            name=name,
            email=email,
            company=company,
            designation=designation,
            industry=industry,
            is_selected=random.choice([True, False]),
            org_id=default_org_id,
        )
        db.add(r)
        recipients.append(r)
    db.flush()

    campaigns_data = [
        ("Q1 Product Launch", "CMP-2024001", "Launch campaign for new product features", "active", 45),
        ("Enterprise Outreach", "CMP-2024002", "Target enterprise clients for upsell", "active", 120),
        ("Holiday Promotion", "CMP-2024003", "End of year promotional campaign", "completed", 200),
        ("Partner Recruitment", "CMP-2024004", "Recruit new channel partners", "draft", 0),
        ("Customer Re-engagement", "CMP-2024005", "Win back inactive customers", "paused", 30),
    ]

    campaigns = []
    for name, cid, desc, status, sent in campaigns_data:
        c = Campaign(
            campaign_name=name,
            campaign_id=cid,
            description=desc,
            owner="Demo User",
            department="Sales",
            target_audience="B2B Decision Makers",
            subject=f"Exclusive offer from {name}",
            status=status,
            emails_sent=sent,
            user_id=user.id,
            org_id=default_org_id,
        )
        db.add(c)
        campaigns.append(c)
    db.flush()

    for i, campaign in enumerate(campaigns[:3]):
        t = Template(
            campaign_id=campaign.id,
            name="Primary Template",
            type=["manual", "placeholder", "ai"][i],
            subject=f"Hello {{{{Name}}}} — Special offer for {{{{Company}}}}",
            body=(
                f"Dear {{{{Name}}}},\n\n"
                f"We noticed {{{{Company}}}} is making strides in the {{{{Industry}}}} sector. "
                f"As {{{{Designation}}}}, you might be interested in our latest solution.\n\n"
                f"Best regards,\nSales Team"
            ),
            closing="Best regards,\nSales Team",
            cta="Schedule a demo",
        )
        db.add(t)

    statuses = ["sent", "sent", "sent", "sent", "failed", "pending"]
    for i in range(30):
        campaign = random.choice(campaigns)
        recipient = random.choice(recipients)
        status = random.choice(statuses)
        log = EmailLog(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status=status,
            error_message="SMTP connection timeout" if status == "failed" else None,
            sent_at=datetime.utcnow() - timedelta(days=random.randint(0, 14), hours=random.randint(0, 23)),
        )
        db.add(log)

    db.commit()
